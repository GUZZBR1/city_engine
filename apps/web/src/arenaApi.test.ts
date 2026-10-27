import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchArena, startArena } from './arenaApi';

function makeArena(overrides: Record<string, unknown> = {}) {
  const ids = ['instance-1', 'instance-2', 'instance-3', 'instance-4', 'instance-5'];
  return {
    arena_id: 'arena-1', status: 'queued', city_id: 'aurora-base-v1', provenance: 'synthetic',
    experiment_id: 'experiment-1', snapshot_id: 'snapshot-1', snapshot_hash: 'snapshot-hash', manifest_hash: 'manifest-hash',
    manifest: { schema_version: '1', profile_id: 'aurora', profile_version: '1', parameter_version: '1', horizon_rounds: 2,
      snapshot_id: 'snapshot-1', snapshot_hash: 'snapshot-hash', generator_version: '1', transition_version: '1', parameters: {}, seeds: {},
      catalog_version: '1', rules_version: '1', provenance: 'synthetic_config', manifest_hash: 'manifest-hash' },
    horizon_rounds: 2, committed_rounds: 0, completed_rounds: 0,
    instances: ids.map((instance_id) => ({ experiment_id: 'experiment-1', instance_id, agent_id: `agent-${instance_id}`,
      policy_id: `policy-${instance_id}`, policy_version: '1', initial_city_state_hash: 'initial-hash',
      current_city_state_hash: 'current-hash', current_round_index: 0, current_state: { experiment_id: 'experiment-1', instance_id, round_index: 0,
        schema_version: '1', transition_version: '1', parent_city_state_hash: null, snapshot_hash: 'snapshot-hash', city_state_hash: 'current-hash',
        population: { residents_by_district: {}, total_residents: 10, urban_residents: 8, rural_catchment_residents: 2 },
        housing: { initialization_method: 'reference', occupied_households_reference_total: 4, occupied_households_urban: 3, vacancy_rate_target: 0.1, units_by_district: {}, total_units: 5 },
        employment: { jobs_by_district: {}, total_jobs: 3 },
        services: { school: { demand_by_district: {}, capacity_by_district: {} }, primary_health: { demand_by_district: {}, capacity_by_district: {} } },
        environment: { public_green_area_m2_by_district: {} },
        budget: { currency: 'credits', credits_per_round: 10, fixed_operations: 1, reserve: 1, discretionary_budget: 8 },
        pending_effects: [], active_signal_plans: [] } })),
    rounds: [], error: null, ...overrides,
  };
}

function makePublishedRound() {
  return { round_index: 1, instances: ['instance-1', 'instance-2', 'instance-3', 'instance-4', 'instance-5'].map((instance_id) => ({
    instance_id, observed_city_state_hash: 'observed-hash', parent_city_state_hash: 'parent-hash', city_state_hash: 'state-hash',
    manifest_hash: 'manifest-hash', round_record_hash: 'record-hash',
    proposal: { schema_version: '1', experiment_id: 'experiment-1', proposal_id: `proposal-${instance_id}`, idempotency_key: `key-${instance_id}`,
      agent_id: `agent-${instance_id}`, instance_id, round_index: 1, observed_city_state_hash: 'observed-hash', actions: [], budget_request: null,
      policy_id: `policy-${instance_id}`, policy_version: '1', proposal_record_hash: 'proposal-hash' },
    decision: { proposal_id: `proposal-${instance_id}`, idempotency_key: `key-${instance_id}`, proposal_hash: 'proposal-hash',
      accepted: false, decision: 'no_action', code: 'no_action', actions: [], budget: null },
    indicators: [{ indicator_id: 'population', indicator_version: '1', value: null, null_reason: 'not_available', unit: 'people',
      unit_basis: 'resident', period: 'year-1', period_type: 'annual', territory: 'city',
      coverage: { status: 'partial', spatial: 'city', temporal: 'annual', numerator: null, denominator: 0, filters: [] },
      formula_version: '1', source_kind: null, production_method: null, source_id: null, source_license: null,
      producer: 'arena', producer_version: '1', parent_state_hash: null, result_hash: null, seed: null, limitations: [] }],
  })) };
}

function makeEvidence() {
  const metrics = { trips_requested: 10, trips_completed: 9, trips_not_completed: 1, mean_travel_time_seconds: 120, mean_speed_kmh: 24, mean_queue_length_meters: 8 };
  return { executor_id: 'sumo-arena-signal-v1', evidence_type: 'paired_sumo_window_comparison', action_ids: ['signal-1'], details: {
    scope: 'simulation_window', provenance: 'synthetic', city_id: 'aurora-base-v1', snapshot_id: 'snapshot-1', snapshot_hash: 'snapshot-hash',
    window_id: 'weekday-am', route_exposure: 'exposed', seed: 42, engine: 'sumo', engine_version: '1.20', base_simulation_id: 'base-run', intervention_simulation_id: 'action-run',
    base_metrics: metrics, intervention_metrics: { ...metrics, mean_travel_time_seconds: 110 },
    deltas: { ...metrics, mean_travel_time_seconds: -10 }, limitations: ['janela sintética'],
  } };
}

describe('Arena API client', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('starts a synthetic arena with the requested horizon and validates HTTP 202', async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe('POST');
      expect(JSON.parse(String(init?.body))).toEqual({ horizon_rounds: 2 });
      return new Response(JSON.stringify({ arena: makeArena() }), { status: 202 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const result = await startArena(2);
    expect(result.status).toBe('queued');
    expect(result.instances).toHaveLength(5);
  });

  it('accepts the real API provenance labels without weakening snapshot identity checks', async () => {
    const arena = makeArena();
    expect(arena.provenance).toBe('synthetic');
    expect(arena.manifest.provenance).toBe('synthetic_config');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena }), { status: 200 })));
    await expect(fetchArena('arena-1')).resolves.toMatchObject({ provenance: 'synthetic', manifest: { provenance: 'synthetic_config' } });

    const badProvenance = makeArena({ manifest: { ...arena.manifest, provenance: 'synthetic' } });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena: badProvenance }), { status: 200 })));
    await expect(fetchArena('arena-1')).rejects.toThrow(/manifest não corresponde à arena sintética/);

    const badSnapshot = makeArena({ manifest: { ...arena.manifest, snapshot_hash: 'different-snapshot-hash' } });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena: badSnapshot }), { status: 200 })));
    await expect(fetchArena('arena-1')).rejects.toThrow(/manifest não corresponde à arena sintética/);
  });

  it('rejects horizons outside the API range before making a request', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(startArena(0)).rejects.toThrow(/inteiro entre 1 e 10/);
    await expect(startArena(11)).rejects.toThrow(/inteiro entre 1 e 10/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fetches an encoded arena id and retains published rounds and nullable values after serialization failure', async () => {
    const arena = makeArena({ arena_id: 'arena/one', status: 'failed', committed_rounds: 2, completed_rounds: 1,
      instances: (makeArena().instances as Record<string, unknown>[]).map((instance) => ({ ...instance, current_round_index: 2, current_state: null })),
      rounds: [makePublishedRound()], error: { code: 'serialization', message: 'could not serialize', round_index: 2, instance_id: null } });
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      expect(String(url)).toBe('http://127.0.0.1:8000/api/v1/arenas/arena%2Fone');
      return new Response(JSON.stringify({ arena }), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);
    const result = await fetchArena('arena/one');
    expect(result.completed_rounds).toBe(1);
    expect(result.committed_rounds).toBe(2);
    expect(result.instances[0].current_state).toBeNull();
    expect(result.rounds[0].instances[0].indicators[0].value).toBeNull();
    expect(result.rounds[0].instances[0].indicators[0].coverage.denominator).toBe(0);
  });

  it('accepts valid action evidence while keeping it optional for older round records', async () => {
    const round = makePublishedRound();
    (round.instances[0] as typeof round.instances[number] & { action_execution_evidence: unknown }).action_execution_evidence = makeEvidence();
    const arena = makeArena({ status: 'succeeded', committed_rounds: 1, completed_rounds: 1, rounds: [round] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena }), { status: 200 })));
    const parsed = await fetchArena('arena-1');
    expect(parsed.rounds[0].instances[0].action_execution_evidence).toMatchObject(makeEvidence());
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena: makeArena({ status: 'succeeded', committed_rounds: 1, completed_rounds: 1, rounds: [makePublishedRound()] }) }), { status: 200 })));
    const legacyParsed = await fetchArena('arena-1');
    expect(legacyParsed.rounds[0].instances[0].action_execution_evidence).toBeUndefined();
  });

  it('rejects malformed action execution evidence fields and metric maps', async () => {
    for (const evidence of [
      { ...makeEvidence(), executor_id: 42 },
      { ...makeEvidence(), evidence_type: null },
      { ...makeEvidence(), action_ids: ['ok', 1] },
      { ...makeEvidence(), details: null },
      { ...makeEvidence(), details: { ...makeEvidence().details, seed: '42' } },
      { ...makeEvidence(), details: { ...makeEvidence().details, base_metrics: { ...makeEvidence().details.base_metrics, mean_speed_kmh: 'fast' } } },
    ]) {
      const round = makePublishedRound();
      (round.instances[0] as typeof round.instances[number] & { action_execution_evidence: unknown }).action_execution_evidence = evidence;
      const arena = makeArena({ status: 'succeeded', committed_rounds: 1, completed_rounds: 1, rounds: [round] });
      vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena }), { status: 200 })));
      await expect(fetchArena('arena-1')).rejects.toThrow(/action_execution_evidence/);
      vi.unstubAllGlobals();
    }
  });

  it('rejects malformed envelopes, identity, status and inconsistent counters', async () => {
    for (const payload of [
      {},
      { arena: { ...makeArena(), status: 'unknown' } },
      { arena: { ...makeArena(), city_id: 'other-city' } },
      { arena: { ...makeArena(), provenance: 'observed' } },
      { arena: { ...makeArena(), committed_rounds: 3 } },
      { arena: { ...makeArena(), instances: (makeArena().instances as unknown[]).slice(0, 4) } },
    ]) {
      vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })));
      await expect(fetchArena('arena-1')).rejects.toThrow(/Resposta inválida da API/);
      vi.unstubAllGlobals();
    }
  });

  it('rejects rounds without exactly five matching instances', async () => {
    const arena = makeArena({ status: 'running', committed_rounds: 1, completed_rounds: 1, rounds: [{ round_index: 1, instances: [] }] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena }), { status: 200 })));
    await expect(fetchArena('arena-1')).rejects.toThrow(/exatamente cinco instâncias/);
  });

  it('rejects published rounds whose index skips the sequence', async () => {
    const round = makePublishedRound();
    round.round_index = 2;
    const arena = makeArena({ status: 'running', committed_rounds: 2, completed_rounds: 1, rounds: [round] });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ arena }), { status: 200 })));
    await expect(fetchArena('arena-1')).rejects.toThrow(/fora de sequência/);
  });

  it('reports HTTP, invalid JSON and network errors clearly', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not found', { status: 404 })));
    await expect(fetchArena('missing')).rejects.toThrow(/HTTP 404/);
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{', { status: 200 })));
    await expect(fetchArena('arena-1')).rejects.toThrow(/não é JSON válido/);
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline'); }));
    await expect(fetchArena('arena-1')).rejects.toThrow(/conectar à API da Arena/);
  });
});
