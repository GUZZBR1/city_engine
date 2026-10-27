import { describe, expect, it } from 'vitest';
import type { ArenaJobDTO } from './arenaApi';
import { createArenaRequestSequence, isArenaPollingStatus, toArenaPanelViewModel } from './arenaViewModel';

function makeJob(overrides: Record<string, unknown> = {}): ArenaJobDTO {
  const ids = Array.from({ length: 5 }, (_, index) => `instance-${index + 1}`);
  const state = (instanceId: string) => ({
    instance_id: instanceId,
    round_index: 1,
    parent_city_state_hash: 'parent-state',
    city_state_hash: 'city-state',
    population: { total_residents: 100, urban_residents: 80, rural_catchment_residents: 20 },
    housing: { total_units: 60, occupied_households_reference_total: 50, vacancy_rate_target: 0.1 },
    employment: { total_jobs: 40 },
    services: {
      school: { demand_by_district: { north: 12, south: 8 }, capacity_by_district: { north: 15, south: 10 } },
      primary_health: { demand_by_district: { north: 4, south: 6 }, capacity_by_district: { north: 5, south: 7 } },
    },
    environment: { public_green_area_m2_by_district: { north: 120, south: 80 } },
  });
  const instances = ids.map((instance_id) => ({
    experiment_id: 'experiment-1', instance_id, agent_id: `agent-${instance_id}`, policy_id: 'no_action', policy_version: '1',
    initial_city_state_hash: 'initial-state', current_city_state_hash: 'city-state', current_round_index: 1,
    current_state: state(instance_id),
  }));
  const evidence = {
    executor_id: 'sumo-arena-signal-v1', evidence_type: 'paired_sumo_window_comparison', action_ids: ['signal-action-1'],
    details: { scope: 'simulation_window', provenance: 'synthetic', city_id: 'aurora-base-v1', snapshot_id: 'snapshot-1', snapshot_hash: 'snapshot-hash',
      window_id: 'weekday-am', route_exposure: 'exposed', seed: 42, engine: 'sumo', engine_version: '1.20', base_simulation_id: 'base-run', intervention_simulation_id: 'action-run',
      base_metrics: { trips_requested: 10, trips_completed: 8, trips_not_completed: 2, mean_travel_time_seconds: 120, mean_speed_kmh: 24, mean_queue_length_meters: 8 },
      intervention_metrics: { trips_requested: 10, trips_completed: 9, trips_not_completed: 1, mean_travel_time_seconds: 110, mean_speed_kmh: 26, mean_queue_length_meters: 6 },
      deltas: { trips_requested: 0, trips_completed: 1, trips_not_completed: -1, mean_travel_time_seconds: -10, mean_speed_kmh: 2, mean_queue_length_meters: -2 }, limitations: ['synthetic'] },
  };
  const rounds = [{ round_index: 1, instances: ids.map((instance_id) => ({
    instance_id,
    observed_city_state_hash: 'observed-state',
    parent_city_state_hash: 'parent-state',
    city_state_hash: 'city-state',
    manifest_hash: 'round-manifest',
    round_record_hash: 'round-record',
    decision: { decision: 'no_action', accepted: false, code: 'no_action', proposal_id: 'proposal', idempotency_key: 'key', proposal_hash: 'proposal-hash', actions: [], budget: null },
    ...(instance_id === 'instance-1' ? { action_execution_evidence: evidence } : {}),
    proposal: {},
    indicators: [{
      indicator_id: 'population_total', value: null, null_reason: 'source_unavailable', unit: 'pessoas', unit_basis: 'residentes',
      period: 'ano 1', period_type: 'annual', territory: 'cidade', coverage: { status: 'complete', spatial: 'city', temporal: 'annual', numerator: 100, denominator: 100, filters: [] },
    }],
  })) }];
  return {
    arena_id: 'arena-1', status: 'succeeded', city_id: 'aurora-base-v1', provenance: 'synthetic', experiment_id: 'experiment-1',
    snapshot_id: 'snapshot-1', snapshot_hash: 'snapshot-hash', manifest_hash: 'manifest-hash',
    manifest: {
      horizon_rounds: 2, provenance: 'synthetic', profile_id: 'reference', profile_version: '1', parameter_version: '1',
      schema_version: '1', generator_version: '1', transition_version: '1', catalog_version: '1', rules_version: '1',
      snapshot_id: 'snapshot-1', snapshot_hash: 'snapshot-hash', parameters: { deterministic: true }, seeds: { base: 42 },
    },
    horizon_rounds: 2, committed_rounds: 1, completed_rounds: 1, instances, rounds, error: null,
    ...overrides,
  } as unknown as ArenaJobDTO;
}

describe('Arena view model adapter', () => {
  it('maps five instances, city state, published decisions, metrics, hashes, and manifest explicitly', () => {
    const result = toArenaPanelViewModel(makeJob());

    expect(result.status).toBe('succeeded');
    expect(result.instances).toHaveLength(5);
    expect(result.instances[0]).toMatchObject({
      instanceId: 'instance-1', policyId: 'no_action', currentRoundIndex: 1,
      currentState: {
        roundIndex: 1, cityStateHash: 'city-state', parentCityStateHash: 'parent-state',
        population: { total: 100, urban: 80, ruralCatchment: 20 },
        housing: { totalUnits: 60, occupiedHouseholds: 50, vacancyRate: 0.1 },
        employment: { totalJobs: 40 },
        services: { schoolDemand: 20, schoolCapacity: 25, primaryHealthDemand: 10, primaryHealthCapacity: 12 },
        publicGreenAreaM2: 200,
      },
    });
    expect(result.rounds[0].instances[0]).toMatchObject({
      observedCityStateHash: 'observed-state', parentCityStateHash: 'parent-state', cityStateHash: 'city-state',
      manifestHash: 'round-manifest', roundRecordHash: 'round-record', decision: 'no_action',
      metrics: [{ id: 'population_total', label: 'population total', value: null, nullReason: 'source_unavailable', unit: 'pessoas', unitBasis: 'residentes', period: 'ano 1' }],
    });
    expect(result.rounds[0].instances[0].actionExecutionEvidence).toMatchObject({
      executorId: 'sumo-arena-signal-v1', evidenceType: 'paired_sumo_window_comparison', actionIds: ['signal-action-1'],
      windowId: 'weekday-am', routeExposure: 'exposed', seed: 42, engine: 'sumo', engineVersion: '1.20', snapshotId: 'snapshot-1', snapshotHash: 'snapshot-hash', limitations: ['synthetic'],
      baseMetrics: { mean_travel_time_seconds: 120 }, interventionMetrics: { mean_travel_time_seconds: 110 }, deltas: { mean_travel_time_seconds: -10 },
    });
    expect(result.manifest).toMatchObject({ hash: 'manifest-hash', snapshotId: 'snapshot-1', profileId: 'reference', provenance: 'synthetic', parameters: { deterministic: true }, seeds: { base: 42 } });
  });

  it('keeps published rounds and confirmed hashes while preserving null current states on failure', () => {
    const source = makeJob({
      status: 'failed', committed_rounds: 2, completed_rounds: 1,
      instances: (makeJob().instances as ArenaJobDTO['instances']).map((instance) => ({ ...instance, current_round_index: 2, current_state: null })),
      error: { code: 'serialization', message: 'round details unavailable', round_index: 2, instance_id: null },
    });
    const result = toArenaPanelViewModel(source);

    expect(result.status).toBe('failed');
    expect(result.rounds).toHaveLength(1);
    expect(result.instances).toHaveLength(5);
    expect(result.instances[0]).toMatchObject({ currentRoundIndex: 2, currentCityStateHash: 'city-state', currentState: null });
    expect(result.error).toEqual({ code: 'serialization', message: 'round details unavailable', roundIndex: 2, instanceId: null });
  });
});

describe('Arena request coordination', () => {
  it('polls only active states', () => {
    expect(isArenaPollingStatus('queued')).toBe(true);
    expect(isArenaPollingStatus('running')).toBe(true);
    expect(isArenaPollingStatus('succeeded')).toBe(false);
    expect(isArenaPollingStatus('failed')).toBe(false);
    expect(isArenaPollingStatus('submitting')).toBe(false);
    expect(isArenaPollingStatus('idle')).toBe(false);
  });

  it('invalidates stale responses when a retry starts or the owner unmounts', () => {
    const sequence = createArenaRequestSequence();
    const first = sequence.begin();
    const second = sequence.begin();
    expect(sequence.isCurrent(first)).toBe(false);
    expect(sequence.isCurrent(second)).toBe(true);

    sequence.invalidate();
    expect(sequence.isCurrent(second)).toBe(false);
  });
});
