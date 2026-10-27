import type { ArenaJobDTO, ArenaJsonObject, ArenaStatus } from './arenaApi';
import type {
  ArenaPanelCityState,
  ArenaPanelInstance,
  ArenaPanelManifest,
  ArenaPanelRound,
  ArenaPanelRoundInstance,
  ArenaPanelStatus,
  ArenaPanelViewModel,
} from './ArenaPanel';

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonRecord : null;
}

function numberAt(source: JsonRecord | null, key: string): number | undefined {
  const value = source?.[key];
  return typeof value === 'number' ? value : undefined;
}

function sumNumbers(value: unknown): number {
  const source = record(value);
  return source ? Object.values(source).reduce<number>((total, item) => total + (typeof item === 'number' ? item : 0), 0) : 0;
}

function cityState(value: ArenaJsonObject | null): ArenaPanelCityState | null {
  if (!value) return null;
  const state = value as JsonRecord;
  const population = record(state.population);
  const housing = record(state.housing);
  const employment = record(state.employment);
  const services = record(state.services);
  const school = record(services?.school);
  const primaryHealth = record(services?.primary_health);
  const environment = record(state.environment);
  const mapped: ArenaPanelCityState = {
    roundIndex: numberAt(state, 'round_index') ?? 0,
    cityStateHash: typeof state.city_state_hash === 'string' ? state.city_state_hash : '',
    parentCityStateHash: typeof state.parent_city_state_hash === 'string' ? state.parent_city_state_hash : null,
  };

  if (population) mapped.population = {
    total: numberAt(population, 'total_residents') ?? 0,
    urban: numberAt(population, 'urban_residents') ?? 0,
    ruralCatchment: numberAt(population, 'rural_catchment_residents') ?? 0,
  };
  if (housing) mapped.housing = {
    totalUnits: numberAt(housing, 'total_units') ?? 0,
    occupiedHouseholds: numberAt(housing, 'occupied_households_reference_total') ?? 0,
    vacancyRate: numberAt(housing, 'vacancy_rate_target') ?? 0,
  };
  if (employment) mapped.employment = { totalJobs: numberAt(employment, 'total_jobs') ?? 0 };
  if (school && primaryHealth) mapped.services = {
    schoolDemand: sumNumbers(school.demand_by_district),
    schoolCapacity: sumNumbers(school.capacity_by_district),
    primaryHealthDemand: sumNumbers(primaryHealth.demand_by_district),
    primaryHealthCapacity: sumNumbers(primaryHealth.capacity_by_district),
  };
  if (environment) mapped.publicGreenAreaM2 = sumNumbers(environment.public_green_area_m2_by_district);
  return mapped;
}

function mapDecision(value: string): ArenaPanelRoundInstance['decision'] {
  if (value === 'accepted' || value === 'rejected' || value === 'no_action') return value;
  throw new Error(`Decisão de Arena não reconhecida: ${value}`);
}

function statusForPanel(status: ArenaStatus): ArenaPanelViewModel['status'] {
  return status;
}

function mapManifest(job: ArenaJobDTO): ArenaPanelManifest {
  const manifest = job.manifest;
  const parameters = record(manifest.parameters) ?? {};
  const seeds = record(manifest.seeds) ?? {};
  return {
    hash: job.manifest_hash,
    snapshotId: job.snapshot_id,
    snapshotHash: job.snapshot_hash,
    profileId: String(manifest.profile_id),
    profileVersion: String(manifest.profile_version),
    parameterVersion: String(manifest.parameter_version),
    schemaVersion: String(manifest.schema_version),
    generatorVersion: String(manifest.generator_version),
    transitionVersion: String(manifest.transition_version),
    catalogVersion: String(manifest.catalog_version),
    rulesVersion: String(manifest.rules_version),
    provenance: String(manifest.provenance),
    parameters,
    seeds: Object.fromEntries(Object.entries(seeds).map(([key, value]) => [key, Number(value)])),
  };
}

function mapRoundInstance(item: ArenaJobDTO['rounds'][number]['instances'][number]): ArenaPanelRoundInstance {
  const extended = item as typeof item & {
    observed_city_state_hash: string;
    parent_city_state_hash: string;
    city_state_hash: string;
    manifest_hash: string;
    round_record_hash: string;
  };
  return {
    instanceId: item.instance_id,
    observedCityStateHash: extended.observed_city_state_hash,
    parentCityStateHash: extended.parent_city_state_hash,
    cityStateHash: extended.city_state_hash,
    manifestHash: extended.manifest_hash,
    roundRecordHash: extended.round_record_hash,
    decision: mapDecision(String(item.decision.decision)),
    actionExecutionEvidence: item.action_execution_evidence ? {
      executorId: item.action_execution_evidence.executor_id,
      evidenceType: item.action_execution_evidence.evidence_type,
      actionIds: item.action_execution_evidence.action_ids,
      windowId: String(item.action_execution_evidence.details.window_id),
      routeExposure: item.action_execution_evidence.details.route_exposure as 'exposed' | 'not_exposed' | 'unknown',
      seed: Number(item.action_execution_evidence.details.seed),
      engine: String(item.action_execution_evidence.details.engine),
      engineVersion: String(item.action_execution_evidence.details.engine_version),
      snapshotId: String(item.action_execution_evidence.details.snapshot_id),
      snapshotHash: String(item.action_execution_evidence.details.snapshot_hash),
      baseSimulationId: String(item.action_execution_evidence.details.base_simulation_id),
      interventionSimulationId: String(item.action_execution_evidence.details.intervention_simulation_id),
      baseMetrics: record(item.action_execution_evidence.details.base_metrics) as Record<string, number | null>,
      interventionMetrics: record(item.action_execution_evidence.details.intervention_metrics) as Record<string, number | null>,
      deltas: record(item.action_execution_evidence.details.deltas) as Record<string, number | null>,
      limitations: item.action_execution_evidence.details.limitations as string[],
    } : item.action_execution_evidence,
    metrics: item.indicators.map((indicator) => ({
      id: indicator.indicator_id,
      label: indicator.indicator_id.replace(/[_-]+/g, ' '),
      value: indicator.value,
      unit: indicator.unit,
      unitBasis: indicator.unit_basis,
      period: indicator.period,
      nullReason: indicator.null_reason,
    })),
  };
}

/** Converts the validated HTTP response into the presentation-only Arena panel contract. */
export function toArenaPanelViewModel(job: ArenaJobDTO): ArenaPanelViewModel {
  const instances: ArenaPanelInstance[] = job.instances.map((instance) => ({
    instanceId: instance.instance_id,
    agentId: instance.agent_id,
    policyId: instance.policy_id,
    policyVersion: instance.policy_version,
    currentRoundIndex: instance.current_round_index,
    currentCityStateHash: instance.current_city_state_hash,
    initialCityStateHash: instance.initial_city_state_hash,
    currentState: cityState(instance.current_state),
  }));
  const rounds: ArenaPanelRound[] = job.rounds.map((round) => ({
    roundIndex: round.round_index,
    instances: round.instances.map(mapRoundInstance),
  }));

  return {
    arenaId: job.arena_id,
    status: statusForPanel(job.status),
    horizonRounds: job.horizon_rounds,
    committedRounds: job.committed_rounds,
    completedRounds: job.completed_rounds,
    manifest: mapManifest(job),
    instances,
    rounds,
    error: job.error ? {
      code: String(job.error.code),
      message: String(job.error.message),
      roundIndex: typeof job.error.round_index === 'number' ? job.error.round_index : null,
      instanceId: typeof job.error.instance_id === 'string' ? job.error.instance_id : null,
    } : null,
  };
}

export function isArenaPollingStatus(status: ArenaPanelStatus | null | undefined): status is 'queued' | 'running' {
  return status === 'queued' || status === 'running';
}

/** A monotonically increasing token invalidates in-flight work on retry and unmount. */
export function createArenaRequestSequence() {
  let current = 0;
  return {
    begin: () => ++current,
    invalidate: () => ++current,
    isCurrent: (generation: number) => generation === current,
  };
}
