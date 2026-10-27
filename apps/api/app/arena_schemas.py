"""HTTP DTOs for process-local Aurora arena jobs.

These schemas are deliberately owned by the API layer. Domain models are
adapted field by field in ``arena_jobs`` rather than exposed directly.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ArenaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_rounds: int = Field(default=10, strict=True, ge=1, le=10)


class ArenaFailure(BaseModel):
    code: str
    message: str
    round_index: int | None = None
    instance_id: str | None = None


class ArenaManifestDTO(BaseModel):
    schema_version: str
    profile_id: str
    profile_version: str
    parameter_version: str
    horizon_rounds: int = Field(ge=1, le=10)
    snapshot_id: str
    snapshot_hash: str
    generator_version: str
    transition_version: str
    parameters: dict[str, Any]
    seeds: dict[str, int]
    catalog_version: str
    rules_version: str
    provenance: str
    manifest_hash: str


class ArenaPopulationStateDTO(BaseModel):
    residents_by_district: dict[str, int]
    total_residents: int
    urban_residents: int
    rural_catchment_residents: int


class ArenaHousingStateDTO(BaseModel):
    initialization_method: str
    occupied_households_reference_total: int
    occupied_households_urban: int
    vacancy_rate_target: float
    units_by_district: dict[str, int]
    total_units: int


class ArenaEmploymentStateDTO(BaseModel):
    jobs_by_district: dict[str, int]
    total_jobs: int


class ArenaServiceDomainStateDTO(BaseModel):
    demand_by_district: dict[str, float]
    capacity_by_district: dict[str, float]


class ArenaServicesStateDTO(BaseModel):
    school: ArenaServiceDomainStateDTO
    primary_health: ArenaServiceDomainStateDTO


class ArenaEnvironmentStateDTO(BaseModel):
    public_green_area_m2_by_district: dict[str, float]


class ArenaBudgetStateDTO(BaseModel):
    currency: str
    credits_per_round: int
    fixed_operations: int
    reserve: int
    discretionary_budget: int


class ArenaEffectiveEventDTO(BaseModel):
    event_id: str
    event_type: str
    effective_round: int
    payload: dict[str, Any]
    source_action_id: str | None


class ArenaCityStateDTO(BaseModel):
    experiment_id: str
    instance_id: str
    round_index: int = Field(ge=0, le=10)
    schema_version: str
    transition_version: str
    parent_city_state_hash: str | None
    snapshot_hash: str
    city_state_hash: str
    population: ArenaPopulationStateDTO
    housing: ArenaHousingStateDTO
    employment: ArenaEmploymentStateDTO
    services: ArenaServicesStateDTO
    environment: ArenaEnvironmentStateDTO
    budget: ArenaBudgetStateDTO
    pending_effects: list[ArenaEffectiveEventDTO]
    active_signal_plans: list[ArenaEffectiveEventDTO]


class ArenaInstanceDTO(BaseModel):
    experiment_id: str
    instance_id: str
    agent_id: str
    policy_id: str
    policy_version: str
    initial_city_state_hash: str
    current_city_state_hash: str
    current_round_index: int = Field(ge=0, le=10)
    current_state: ArenaCityStateDTO | None = Field(
        description="Nulo somente quando o estado confirmado não pôde ser serializado; hash e round atuais continuam disponíveis."
    )


class ArenaIndicatorCoverageDTO(BaseModel):
    status: str
    spatial: str
    temporal: str
    numerator: int | float | None
    denominator: int | float | None
    filters: list[str]


class ArenaIndicatorDTO(BaseModel):
    indicator_id: str
    indicator_version: str
    value: int | float | None
    null_reason: str | None
    unit: str
    unit_basis: str
    period: str
    period_type: str
    territory: str
    coverage: ArenaIndicatorCoverageDTO
    formula_version: str
    source_kind: str | None
    production_method: str | None
    source_id: str | None
    source_license: str | None
    producer: str
    producer_version: str
    parent_state_hash: str | None
    result_hash: str | None
    seed: int | None
    limitations: list[str]


class ArenaBudgetChargeDTO(BaseModel):
    round_index: int
    amount_cs: int
    kind: Literal["one_time", "recurring"]
    source_action_id: str


class ArenaRoundBudgetDTO(BaseModel):
    round_index: int
    limit_cs: int
    already_committed_cs: int
    proposed_cs: int
    available_cs: int


class ArenaBudgetAssessmentDTO(BaseModel):
    accepted: bool
    code: Literal["within_budget", "budget_exceeded", "commitment_outside_horizon"]
    rounds: list[ArenaRoundBudgetDTO]
    charges: list[ArenaBudgetChargeDTO]


class ArenaProposalActionDTO(BaseModel):
    action_id: str
    action_type: Literal["signal_timing_change", "housing_add_units", "service_capacity_contract"]
    target_id: str
    parameters: dict[str, Any]
    rationale: str | None


class ArenaActionReceiptDTO(BaseModel):
    action_id: str
    action_type: str
    accepted: bool
    code: str
    message: str
    charges: list[ArenaBudgetChargeDTO]
    effective_round: int | None
    conflict_key: str | None


class ArenaDecisionDTO(BaseModel):
    proposal_id: str
    idempotency_key: str
    proposal_hash: str
    accepted: bool
    decision: Literal["accepted", "rejected", "no_action"]
    code: str
    actions: list[ArenaActionReceiptDTO]
    budget: ArenaBudgetAssessmentDTO | None


class ArenaProposalDTO(BaseModel):
    schema_version: str
    experiment_id: str
    proposal_id: str
    idempotency_key: str
    agent_id: str
    instance_id: str
    round_index: int
    observed_city_state_hash: str
    actions: list[ArenaProposalActionDTO]
    budget_request: int | None
    policy_id: str
    policy_version: str
    proposal_record_hash: str


class ArenaRoundInstanceDTO(BaseModel):
    instance_id: str
    proposal: ArenaProposalDTO
    decision: ArenaDecisionDTO
    action_execution_evidence: dict[str, Any] | None = None
    indicators: list[ArenaIndicatorDTO]
    observed_city_state_hash: str
    parent_city_state_hash: str
    city_state_hash: str
    manifest_hash: str
    round_record_hash: str


class ArenaRoundDTO(BaseModel):
    round_index: int = Field(ge=1, le=10)
    instances: list[ArenaRoundInstanceDTO] = Field(min_length=5, max_length=5)


class ArenaJob(BaseModel):
    arena_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    city_id: Literal["aurora-base-v1"]
    provenance: Literal["synthetic"]
    experiment_id: str
    snapshot_id: str
    snapshot_hash: str
    manifest_hash: str
    manifest: ArenaManifestDTO
    horizon_rounds: int = Field(ge=1, le=10)
    committed_rounds: int = Field(
        ge=0,
        le=10,
        description="Rodadas confirmadas pelo ArenaRunner, inclusive quando detalhes da API falham ao serializar.",
    )
    completed_rounds: int = Field(
        ge=0,
        le=10,
        description="Rodadas cujos detalhes foram integralmente serializados e publicados em rounds.",
    )
    instances: list[ArenaInstanceDTO] = Field(min_length=5, max_length=5)
    rounds: list[ArenaRoundDTO] = Field(default_factory=list)
    error: ArenaFailure | None = None


class ArenaResponse(BaseModel):
    arena: ArenaJob
