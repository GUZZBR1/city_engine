"""Policy boundary and deterministic reference policy for Aurora proposals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .actions import ActionProposal
from .observations import Observation


@runtime_checkable
class AgentPolicy(Protocol):
    """A policy converts one frozen observation into a proposal."""

    agent_id: str
    policy_id: str
    policy_version: str

    def propose(self, observation: Observation) -> ActionProposal:
        """Return exactly one proposal for the supplied observation."""


@dataclass(frozen=True, slots=True)
class DeterministicReferencePolicy:
    """Stable baseline that makes no discretionary intervention."""

    agent_id: str = "reference-agent"
    policy_id: str = "deterministic-reference"
    policy_version: str = "1"

    def propose(self, observation: Observation) -> ActionProposal:
        experiment_id = str(observation.state_view["experiment_id"])
        payload = {
            "experiment_id": experiment_id,
            "agent_id": self.agent_id,
            "instance_id": observation.instance_id,
            "round_index": observation.round_index,
            "observed_city_state_hash": observation.city_state_hash,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "actions": [],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        proposal_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        identity = json.dumps(
            {
                "experiment_id": experiment_id,
                "instance_id": observation.instance_id,
                "round_index": observation.round_index,
                "agent_id": self.agent_id,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return ActionProposal(
            experiment_id=experiment_id,
            proposal_id=proposal_id,
            idempotency_key=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            agent_id=self.agent_id,
            instance_id=observation.instance_id,
            round_index=observation.round_index,
            observed_city_state_hash=observation.city_state_hash,
            actions=(),
        )
