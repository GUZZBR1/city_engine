"""Process-local CAS repository for atomic five-instance Aurora rounds."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from threading import RLock

from .actions import ActionProposal, ArbitrationDecision
from .indicators import IndicatorValue
from .state import CityState, StateTransitionResult, canonical_hash

INSTANCE_COUNT = 5


class RepositoryConflictError(RuntimeError):
    """An identity was reused with different content or a stale parent hash."""


@dataclass(frozen=True, slots=True)
class ProposalRecord:
    """Canonical agent proposal plus policy identity/version provenance."""

    proposal: ActionProposal
    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("policy_id e policy_version são obrigatórios")

    @property
    def identity(self) -> tuple[str, str, int, str, str]:
        proposal = self.proposal
        return (
            proposal.experiment_id,
            proposal.instance_id,
            proposal.round_index,
            self.policy_id,
            self.policy_version,
        )

    @property
    def content_hash(self) -> str:
        return canonical_hash({
            "proposal": self.proposal.model_dump(mode="json"),
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
        })


@dataclass(frozen=True, slots=True)
class RoundRecord:
    """Committed round receipt, using shared proposal/decision/state/indicator types."""

    proposal_record: ProposalRecord
    decision: ArbitrationDecision
    indicator_results: tuple[IndicatorValue, ...]
    state_transition: StateTransitionResult
    observed_city_state_hash: str
    diagnostics: tuple[str, ...] = ()

    @property
    def round_record_hash(self) -> str:
        return canonical_hash({
            "proposal_record_hash": self.proposal_record.content_hash,
            "decision": self.decision.model_dump(mode="json"),
            "indicator_results": [value.model_dump(mode="json") for value in self.indicator_results],
            "state_transition": self.state_transition.model_dump(mode="json"),
            "observed_city_state_hash": self.observed_city_state_hash,
            "diagnostics": list(self.diagnostics),
        })

    @property
    def experiment_id(self) -> str:
        return self.state_transition.experiment_id

    @property
    def instance_id(self) -> str:
        return self.state_transition.instance_id

    @property
    def round_index(self) -> int:
        return self.state_transition.round_index

    @property
    def parent_city_state_hash(self) -> str:
        return self.state_transition.parent_city_state_hash


def _clone_record(record: RoundRecord) -> RoundRecord:
    return copy.deepcopy(record)


class InMemoryRoundRepository:
    """Atomic state/proposal/round-result repository for one five-agent experiment.

    This implementation provides process-local compare-and-swap and retry
    semantics only. It does not promise durability or cross-process locking.
    """

    def __init__(self, initial_states: Sequence[CityState]) -> None:
        if len(initial_states) != INSTANCE_COUNT:
            raise ValueError(f"repositório exige exatamente {INSTANCE_COUNT} estados iniciais")
        experiment_ids = {state.experiment_id for state in initial_states}
        instance_ids = {state.instance_id for state in initial_states}
        if len(experiment_ids) != 1 or len(instance_ids) != INSTANCE_COUNT:
            raise ValueError("estados iniciais devem pertencer a um experimento e ter instâncias únicas")
        if {state.round_index for state in initial_states} != {0}:
            raise ValueError("estados iniciais devem começar na rodada 0")
        if len({state.snapshot_hash for state in initial_states}) != 1:
            raise ValueError("estados iniciais devem compartilhar o mesmo snapshot raiz")
        if len({state.city_state_hash for state in initial_states}) != 1:
            raise ValueError("estados iniciais devem ter conteúdo e hash de cidade equivalentes")

        self._experiment_id = next(iter(experiment_ids))
        self._states = {state.instance_id: state.model_copy(deep=True) for state in initial_states}
        self._proposals: dict[tuple[str, str, int, str, str], ProposalRecord] = {}
        self._rounds: dict[tuple[str, str, int, str], RoundRecord] = {}
        self._lock = RLock()

    @property
    def experiment_id(self) -> str:
        return self._experiment_id

    @property
    def instance_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._states))

    def load_state(self, instance_id: str) -> CityState:
        with self._lock:
            try:
                state = self._states[instance_id]
            except KeyError as exc:
                raise KeyError(f"instância desconhecida: {instance_id}") from exc
            return state.model_copy(deep=True)

    def load_states(self) -> tuple[CityState, ...]:
        with self._lock:
            return tuple(self._states[instance_id].model_copy(deep=True) for instance_id in self.instance_ids)

    @property
    def recorded_proposals(self) -> tuple[ProposalRecord, ...]:
        with self._lock:
            return tuple(
                copy.deepcopy(self._proposals[key]) for key in sorted(self._proposals)
            )

    def record_proposal(self, record: ProposalRecord) -> ProposalRecord:
        """Record the policy's original proposal before arbitration/evaluation."""
        proposal = record.proposal
        if proposal.experiment_id != self._experiment_id:
            raise ValueError("proposta pertence a outro experimento")
        if proposal.instance_id not in self._states:
            raise ValueError(f"proposta referencia instância desconhecida: {proposal.instance_id}")

        key = record.identity
        with self._lock:
            existing = self._proposals.get(key)
            if existing is not None:
                if existing.content_hash != record.content_hash:
                    raise RepositoryConflictError(f"identidade da proposta reutilizada com conteúdo diferente: {key}")
                return copy.deepcopy(existing)

            if any(
                prior.proposal.experiment_id == proposal.experiment_id
                and prior.proposal.instance_id == proposal.instance_id
                and prior.proposal.round_index == proposal.round_index
                for prior in self._proposals.values()
            ):
                raise RepositoryConflictError("já existe uma proposta gravada para esta instância/rodada")

            saved = copy.deepcopy(record)
            self._proposals[key] = saved
            return copy.deepcopy(saved)

    def load_proposal(
        self,
        experiment_id: str,
        instance_id: str,
        round_index: int,
        policy_id: str,
        policy_version: str,
    ) -> ProposalRecord | None:
        """Replay a recorded policy proposal without invoking the participant again."""
        key = (experiment_id, instance_id, round_index, policy_id, policy_version)
        with self._lock:
            record = self._proposals.get(key)
            return copy.deepcopy(record) if record is not None else None

    def commit_round(self, records: Sequence[RoundRecord]) -> tuple[RoundRecord, ...]:
        """CAS and publish the complete five-instance round as one memory operation.

        All identity, retry, and parent-hash checks happen before either state or
        round records are mutated. On any error the confirmed state is untouched.
        """
        if len(records) != INSTANCE_COUNT:
            raise ValueError(f"round commit exige exatamente {INSTANCE_COUNT} registros")
        if any(record.experiment_id != self._experiment_id for record in records):
            raise ValueError("round commit mistura experimentos")
        round_indexes = {record.round_index for record in records}
        instance_ids = [record.instance_id for record in records]
        if len(round_indexes) != 1 or set(instance_ids) != set(self._states):
            raise ValueError("round commit exige uma rodada e exatamente as cinco instâncias")

        with self._lock:
            round_index = next(iter(round_indexes))
            commit_keys = [
                (record.experiment_id, record.instance_id, round_index, record.parent_city_state_hash)
                for record in records
            ]
            saved_records = [self._rounds.get(key) for key in commit_keys]
            if any(record is not None for record in saved_records):
                if not all(record is not None for record in saved_records):
                    raise RepositoryConflictError("round commit anterior ficou incompleto")
                prior_by_instance = {
                    record.instance_id: record for record in saved_records if record is not None
                }
                incoming_by_instance = {record.instance_id: record for record in records}
                if any(
                    prior_by_instance[instance_id].round_record_hash
                    != incoming_by_instance[instance_id].round_record_hash
                    for instance_id in self._states
                ):
                    raise RepositoryConflictError("identidade da rodada reutilizada com conteúdo diferente")
                return tuple(
                    _clone_record(prior_by_instance[instance_id])
                    for instance_id in sorted(self._states)
                )

            for record in records:
                proposal = record.proposal_record.proposal
                if (
                    proposal.experiment_id != record.experiment_id
                    or proposal.instance_id != record.instance_id
                    or proposal.round_index != round_index
                    or proposal.observed_city_state_hash != record.observed_city_state_hash
                ):
                    raise ValueError("proposta gravada não corresponde à observação/hash do round record")
                if (
                    record.decision.proposal_id != proposal.proposal_id
                    or record.decision.idempotency_key != proposal.idempotency_key
                ):
                    raise ValueError("decisão de arbitragem não corresponde à proposta gravada")
                if self._proposals.get(record.proposal_record.identity) is None:
                    raise ValueError("proposta deve ser gravada antes do commit da rodada")
                if self._proposals[record.proposal_record.identity].content_hash != record.proposal_record.content_hash:
                    raise RepositoryConflictError("round record diverge da proposta gravada")

                transition = record.state_transition
                candidate = transition.candidate_state
                if candidate is None:
                    raise ValueError("round record exige candidate_state confirmado")
                if (
                    transition.experiment_id != record.experiment_id
                    or transition.instance_id != record.instance_id
                    or transition.round_index != round_index
                    or transition.parent_city_state_hash != record.parent_city_state_hash
                ):
                    raise ValueError("StateTransitionResult não corresponde à identidade/estado pai da rodada")
                if transition.manifest_hash == "" or transition.delta.parent_city_state_hash != record.parent_city_state_hash:
                    raise ValueError("StateTransitionResult inválido para commit")
                if candidate.city_state_hash != transition.city_state_hash:
                    raise ValueError("hash do candidate_state não corresponde ao StateTransitionResult")
                if candidate.round_index != round_index:
                    raise ValueError("candidate_state não corresponde à rodada do round record")

                current = self._states[record.instance_id]
                if current.city_state_hash != record.parent_city_state_hash:
                    raise RepositoryConflictError(
                        f"compare-and-swap falhou para {record.instance_id}: estado pai mudou"
                    )
                if candidate.round_index != current.round_index + 1:
                    raise ValueError("candidate_state deve avançar exatamente uma rodada confirmada")
                if candidate.parent_city_state_hash != current.city_state_hash:
                    raise ValueError("candidate_state deve referenciar o hash confirmado atual")

            # All checks passed. Prepare deep copies before the mutation boundary.
            state_updates = {
                record.instance_id: record.state_transition.candidate_state.model_copy(deep=True)
                for record in records
                if record.state_transition.candidate_state is not None
            }
            round_updates = {
                key: _clone_record(record) for key, record in zip(commit_keys, records, strict=True)
            }
            self._states.update(state_updates)
            self._rounds.update(round_updates)
            return tuple(_clone_record(record) for record in sorted(records, key=lambda item: item.instance_id))

    def load_round(self, experiment_id: str, instance_id: str, round_index: int) -> RoundRecord:
        """Load the latest round record for an instance/round, independent of parent hash."""
        with self._lock:
            matches = [
                record
                for key, record in self._rounds.items()
                if key[:3] == (experiment_id, instance_id, round_index)
            ]
            if len(matches) != 1:
                if not matches:
                    raise KeyError("round record não encontrado")
                raise RepositoryConflictError("mais de um round record para a identidade solicitada")
            return _clone_record(matches[0])

    def recorded_round(self, experiment_id: str, round_index: int) -> tuple[RoundRecord, ...]:
        """Return the five committed records for one atomic experiment round."""
        with self._lock:
            records = [
                record
                for key, record in self._rounds.items()
                if key[0] == experiment_id and key[2] == round_index
            ]
            if not records:
                raise KeyError("round records não encontrados")
            if len(records) != INSTANCE_COUNT:
                raise RepositoryConflictError("round commit armazenado está incompleto")
            return tuple(_clone_record(record) for record in sorted(records, key=lambda item: item.instance_id))
