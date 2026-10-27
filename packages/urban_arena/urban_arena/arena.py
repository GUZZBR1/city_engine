"""Five-instance annual Aurora arena with a proposal barrier and atomic commits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .actions import ActionCatalog, ActionProposal, SignalTarget
from .indicators import IndicatorValue
from .manifest import ExperimentManifest, build_aurora_synthetic_v1_manifest
from .models import CityConfigFile, CitySnapshot
from .observations import Observation
from .repository import (
    InMemoryRoundRepository,
    ProposalRecord,
    RepositoryConflictError,
    RoundRecord,
)
from .round_engine import ActionExecutor, AnnualRoundEngine
from .state import CityState, StateFactory

INSTANCE_COUNT = 5
DEFAULT_HORIZON_ROUNDS = 10
ProposalConflictError = RepositoryConflictError


class ParticipantFailure(RuntimeError):
    """A participant failed; no city state is committed for the round."""

    def __init__(self, instance_id: str, round_index: int, cause: Exception) -> None:
        super().__init__(f"política falhou para {instance_id} na rodada {round_index}: {cause}")
        self.instance_id = instance_id
        self.round_index = round_index
        self.__cause__ = cause


@dataclass(frozen=True, slots=True)
class ArenaInstance:
    """Stable instance identity and initial evolutive-state hash."""

    experiment_id: str
    instance_id: str
    initial_city_state_hash: str


class ArenaRunner:
    """Coordinate frozen proposals and ten atomic annual transitions in memory."""

    def __init__(
        self,
        snapshot: CitySnapshot,
        experiment_id: str | None = None,
        *,
        manifest: ExperimentManifest | None = None,
        catalog: ActionCatalog | None = None,
        signal_targets: Sequence[SignalTarget] = (),
        action_executor: ActionExecutor | None = None,
    ) -> None:
        if manifest is None:
            if not experiment_id:
                raise ValueError("experiment_id ou manifest são obrigatórios")
            city_config = CityConfigFile.model_validate(snapshot.source_config)
            manifest = build_aurora_synthetic_v1_manifest(
                city_config,
                snapshot,
                experiment_id=experiment_id,
            )
        elif experiment_id is not None and experiment_id != manifest.experiment_id:
            raise ValueError("experiment_id não corresponde ao manifesto")
        if manifest.snapshot_hash != snapshot.hash or manifest.snapshot_id != snapshot.snapshot_id:
            raise ValueError("manifesto e snapshot devem apontar para a mesma raiz")

        self.manifest = manifest
        self.experiment_id = manifest.experiment_id
        self._instance_ids = tuple(
            f"{self.experiment_id}:instance:{index:02d}"
            for index in range(1, INSTANCE_COUNT + 1)
        )
        initial_states = StateFactory.copies(
            snapshot,
            manifest=manifest,
            instance_ids=list(self._instance_ids),
        )
        self.repository = InMemoryRoundRepository(initial_states)
        engine_options = {
            "signal_targets": signal_targets,
            "action_executor": action_executor,
        }
        if catalog is not None:
            engine_options["catalog"] = catalog
        self.round_engine = AnnualRoundEngine(manifest, **engine_options)
        self._instances = tuple(
            ArenaInstance(
                experiment_id=self.experiment_id,
                instance_id=state.instance_id,
                initial_city_state_hash=state.city_state_hash,
            )
            for state in initial_states
        )

    @property
    def instances(self) -> tuple[ArenaInstance, ...]:
        return self._instances

    @property
    def recorded_proposals(self) -> tuple[ProposalRecord, ...]:
        return self.repository.recorded_proposals

    def state_copy(self, instance_id: str) -> CityState:
        """Return a defensive evolutive-state copy, never the repository-owned state."""
        return self.repository.load_state(instance_id)

    def observation(self, instance_id: str, round_index: int) -> Observation:
        state = self.repository.load_state(instance_id)
        if round_index != state.round_index + 1:
            raise ValueError("observação deve usar a próxima rodada ainda não confirmada")
        previous = self._previous_indicators(instance_id, state.round_index)
        _, observation = self.round_engine.prepare_observation(
            state,
            previous_indicators=previous,
        )
        if observation.round_index != round_index:
            raise ValueError("round_index solicitado não corresponde ao candidato observado")
        return observation

    def run_round(
        self,
        round_index: int,
        policies: Sequence[AgentPolicy],
    ) -> tuple[RoundRecord, ...]:
        """Collect and record proposals, compute all five results, then CAS commit."""
        self._validate_round(round_index)
        if len(policies) != INSTANCE_COUNT:
            raise ValueError(f"são necessárias exatamente {INSTANCE_COUNT} políticas")
        saved_round = self._committed_round(round_index)
        if saved_round is not None:
            self._validate_retry_policies(saved_round, policies)
            return saved_round

        parents = self.repository.load_states()
        if any(parent.round_index + 1 != round_index for parent in parents):
            raise ValueError("rodada deve avançar exatamente uma vez em todas as instâncias")
        previous_indicators = {
            parent.instance_id: self._previous_indicators(parent.instance_id, parent.round_index)
            for parent in parents
        }
        prepared = tuple(
            self.round_engine.prepare_observation(
                parent,
                previous_indicators=previous_indicators[parent.instance_id],
            )
            for parent in parents
        )
        # Freeze every instance's observation before invoking any participant.
        observations = tuple(item[1] for item in prepared)

        proposal_records: list[ProposalRecord] = []
        for parent, observation, policy in zip(parents, observations, policies, strict=True):
            recorded = self.repository.load_proposal(
                self.experiment_id,
                parent.instance_id,
                round_index,
                policy.policy_id,
                policy.policy_version,
            )
            if recorded is not None:
                if recorded.proposal.agent_id != policy.agent_id:
                    raise RepositoryConflictError("agent_id mudou para uma identidade de política já gravada")
                proposal_records.append(recorded)
                continue

            try:
                proposal = policy.propose(observation)
            except Exception as exc:
                raise ParticipantFailure(parent.instance_id, round_index, exc) from exc
            self._validate_proposal(proposal, policy, observation)
            proposal_records.append(
                self.repository.record_proposal(
                    ProposalRecord(
                        proposal=proposal,
                        policy_id=policy.policy_id,
                        policy_version=policy.policy_version,
                    )
                )
            )

        round_records = tuple(
            self.round_engine.execute_round(
                parent,
                prepared_candidate,
                observation,
                proposal_record,
            )
            for parent, (prepared_candidate, observation), proposal_record in zip(
                parents,
                prepared,
                proposal_records,
                strict=True,
            )
        )
        return self.repository.commit_round(round_records)

    @property
    def transition_dependency(self) -> str:
        """Remaining non-integrated action/effect boundary, not the annual engine."""
        return "durable repository and SUMO/action application adapter for currently disabled actions"

    def _previous_indicators(
        self,
        instance_id: str,
        round_index: int,
    ) -> tuple[IndicatorValue, ...]:
        if round_index == 0:
            return ()
        return self.repository.load_round(
            self.experiment_id,
            instance_id,
            round_index,
        ).indicator_results

    def _committed_round(self, round_index: int) -> tuple[RoundRecord, ...] | None:
        try:
            return self.repository.recorded_round(self.experiment_id, round_index)
        except KeyError:
            return None

    def _validate_retry_policies(
        self,
        records: tuple[RoundRecord, ...],
        policies: Sequence[AgentPolicy],
    ) -> None:
        policies_by_instance = dict(zip(self._instance_ids, policies, strict=True))
        for record in records:
            policy = policies_by_instance[record.instance_id]
            provenance = record.proposal_record
            if (
                provenance.policy_id != policy.policy_id
                or provenance.policy_version != policy.policy_version
                or provenance.proposal.agent_id != policy.agent_id
            ):
                raise RepositoryConflictError("retry da rodada reutiliza identidade de política diferente")

    @staticmethod
    def _validate_proposal(
        proposal: ActionProposal,
        policy: AgentPolicy,
        observation: Observation,
    ) -> None:
        if not isinstance(proposal, ActionProposal):
            raise TypeError("AgentPolicy.propose deve retornar actions.ActionProposal")
        if proposal.agent_id != policy.agent_id:
            raise ValueError("agent_id da proposta diverge da política")
        if (
            proposal.experiment_id != str(observation.state_view["experiment_id"])
            or proposal.instance_id != observation.instance_id
            or proposal.round_index != observation.round_index
            or proposal.observed_city_state_hash != observation.city_state_hash
        ):
            raise ValueError("proposta diverge da observação congelada")

    def _validate_round(self, round_index: int) -> None:
        if type(round_index) is not int:
            raise TypeError("round_index deve ser inteiro")
        if not 1 <= round_index <= self.manifest.horizon_rounds:
            raise ValueError("round_index excede o horizonte congelado no manifesto")


if TYPE_CHECKING:
    from .policies import AgentPolicy
