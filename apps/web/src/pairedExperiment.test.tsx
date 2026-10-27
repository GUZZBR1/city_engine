import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MetricProvenanceCell, PairedExperimentPanel } from './PairedExperimentPanel';
import { computePolicySha256, parsePairedExperiment, type ExpectedExperimentPlan } from './pairedExperiment';
import { failedPairWithStaleDeltaFixture, pairedExperimentContractFixture } from './pairedExperiment.contract.fixture';

const copy = (): { experiment: Record<string, any> } => structuredClone(pairedExperimentContractFixture) as { experiment: Record<string, any> };
const expectedPlan = { window_ids: ['weekday_am_peak'], strategies: structuredClone(pairedExperimentContractFixture.experiment.manifest.strategies), seeds: [41, 42], metrics: ['trips_completed', 'mean_queue_length_meters'], primary_metrics: ['trips_completed'] } as ExpectedExperimentPlan;

describe('paired multi-seed DTO v1.0 adapter', () => {
  it('accepts the API envelope and frozen plan, including zero and unavailable metrics', () => {
    const parsed = parsePairedExperiment(copy(), expectedPlan);
    expect(parsed.dto_schema_version).toBe('1.0');
    expect(parsed.pairs).toHaveLength(2);
    expect(parsed.pairs[0].baseline_metrics?.trips_completed.value).toBe(0);
    expect(parsed.pairs[0].baseline_metrics?.mean_queue_length_meters.value).toBeNull();
    expect(parsed.pairs[0].deltas?.trips_completed.source_artifact_sha256).toHaveLength(2);
    expect(parsed.summaries_by_window.find((summary) => summary.metric_id === 'trips_completed')?.arm_summary).toHaveProperty('baseline');
    expect(() => parsePairedExperiment(copy(), { ...expectedPlan, window_ids: ['weekday_off_peak'] })).toThrow(/manifesto retornado diverge/);
  });

  it('accepts valid partial and queued experiments', () => {
    expect(parsePairedExperiment(structuredClone(failedPairWithStaleDeltaFixture)).status).toBe('partial');

    const queued = copy();
    queued.experiment.status = 'queued';
    queued.experiment.completed_pairs = 0;
    queued.experiment.missing_pairs = 2;
    queued.experiment.missing_pair_ids = ['pair-41', 'pair-42'];
    queued.experiment.attempts = 0;
    queued.experiment.sumo_runs_used = 0;
    queued.experiment.pairs = queued.experiment.pairs.map((pair: any) => ({
      ...pair, status: 'queued', baseline_metrics: {}, strategy_metrics: {}, deltas: {},
      executions: Object.fromEntries(['baseline', 'strategy'].map((arm) => [arm, {
        ...pair.executions[arm], status: 'queued', attempts: [{ ...pair.executions[arm].attempts[0], attempt: 1, status: 'queued', artifact_sha256: null, wall_clock_seconds: 0 }],
        result_metrics: null, artifact_sha256: null, artifacts: {},
      }])),
    }));
    queued.experiment.summaries_by_window = queued.experiment.summaries_by_window.map((summary: any) => ({
      ...summary, n_complete: 0,
      arm_summary: { baseline: { mean: null, sd: null, median: null, iqr: null, min: null, max: null }, strategy: { mean: null, sd: null, median: null, iqr: null, min: null, max: null } },
      paired_delta_summary: { mean: null, sd: null, median: null, iqr: null, min: null, max: null },
      confidence_interval: { ...summary.confidence_interval, n: 0, degrees_of_freedom: null, lower: null, upper: null },
    }));
    expect(parsePairedExperiment(queued).status).toBe('queued');
  });

  it('rejects contradictory aggregate counts, experiment status, and summary counts', () => {
    const wrongCounts = copy();
    wrongCounts.experiment.missing_pairs = 1;
    expect(() => parsePairedExperiment(wrongCounts)).toThrow(/contadores não reconciliam/);

    const wrongStatus = copy();
    wrongStatus.experiment.status = 'succeeded';
    wrongStatus.experiment.pairs[0].status = 'queued';
    wrongStatus.experiment.pairs[0].baseline_metrics = {};
    wrongStatus.experiment.pairs[0].strategy_metrics = {};
    wrongStatus.experiment.pairs[0].deltas = {};
    wrongStatus.experiment.completed_pairs = 1;
    wrongStatus.experiment.missing_pairs = 1;
    wrongStatus.experiment.missing_pair_ids = ['pair-41'];
    expect(() => parsePairedExperiment(wrongStatus)).toThrow(/succeeded com pares incompletos/);

    const wrongSummary = copy();
    wrongSummary.experiment.summaries_by_window[0].n_complete = 1;
    wrongSummary.experiment.summaries_by_window[0].confidence_interval.n = 1;
    wrongSummary.experiment.summaries_by_window[0].confidence_interval.degrees_of_freedom = null;
    wrongSummary.experiment.summaries_by_window[0].confidence_interval.lower = null;
    wrongSummary.experiment.summaries_by_window[0].confidence_interval.upper = null;
    expect(() => parsePairedExperiment(wrongSummary)).toThrow(/n do resumo diverge/);
  });

  it('rejects malformed hashes, duplicate cells, and delta source hashes without both artifacts', () => {
    const badHash = copy();
    badHash.experiment.manifest_sha256 = 'not-a-sha';
    expect(() => parsePairedExperiment(badHash)).toThrow(/SHA-256/);
    const duplicate = copy();
    duplicate.experiment.pairs[1] = structuredClone(duplicate.experiment.pairs[0]);
    expect(() => parsePairedExperiment(duplicate)).toThrow(/duplicada/);
    const missingDeltaSource = copy();
    missingDeltaSource.experiment.pairs[0].deltas.trips_completed.source_artifact_sha256 = ['d'.repeat(64)];
    expect(() => parsePairedExperiment(missingDeltaSource)).toThrow(/dois artefatos de origem/);
  });
});

describe('paired experiment form accessibility markup', () => {
  it('uses a labeled, explicit window fieldset and exposes loading/error accessible regions', () => {
    const html = renderToStaticMarkup(<PairedExperimentPanel />);
    expect(html).toContain('<fieldset');
    expect(html).toContain('<legend>Janelas configuradas');
    expect(html).toContain('weekday_am_peak');
    expect(html).toContain('weekday_off_peak');
    expect(html).toContain('aria-labelledby="paired-experiment-title"');
    expect(html).toContain('Acompanhar experimento existente');
  });

  it('renders metric provenance and full artifact hashes separately for each arm', () => {
    const pair = parsePairedExperiment(copy()).pairs[0];
    const baseline = { ...pair.baseline_metrics!.trips_completed, artifact_sha256: 'a'.repeat(64) };
    const strategy = { ...pair.strategy_metrics!.trips_completed, artifact_sha256: 'b'.repeat(64) };
    const html = renderToStaticMarkup(<table><tbody><tr><MetricProvenanceCell baseline={baseline} strategy={strategy} delta={pair.deltas!.trips_completed} /></tr></tbody></table>);
    expect(html).toContain('Baseline:');
    expect(html).toContain('Estratégia:');
    expect(html).toContain('Delta:');
    expect(html).toContain('a'.repeat(64));
    expect(html).toContain('b'.repeat(64));
  });
});

describe('mobility-experiments HTTP adapter', () => {
  const createInput = {
    arena_manifest_id: 'arena-manifest-001', arena_manifest_sha256: 'a'.repeat(64), round_index: 1,
    instance_id: 'aurora-instance-001', city_id: 'aurora-base-v1' as const,
    window_ids: ['weekday_am_peak'], seeds: [41, 42],
    strategies: [{ strategy_id: 'signal_timing_node_02_04', policy_version: '1', policy_sha256: 'b'.repeat(64), intervention: { node_id: 'node_02_04', phases: [{ movement: 'north_south' as const, duration_seconds: 30 }, { movement: 'east_west' as const, duration_seconds: 30 }] } }],
    baseline_id: 'aurora-default', baseline_version: '1', baseline_sha256: 'c'.repeat(64), drain_limit_seconds: 300,
    metrics: ['trips_completed', 'mean_queue_length_meters'], metric_tolerances: { trips_completed: { exact: true }, mean_queue_length_meters: { absolute: 0, relative: 0 } },
    method_version: 'sumo-metrics-v1', budget: { max_sumo_runs: 4, max_attempts_per_execution: 2, max_reproducibility_checks: 0, max_wall_clock_seconds_per_run: 60, max_total_wall_clock_seconds: 240, admit_incomplete: true },
    reproducibility_checks: 0, selection_method: 'externally_predeclared', master_seed: 9001, primary_metrics: ['trips_completed'], confidence_level: 0.95,
  };
  it('posts the API nested create DTO and parses the 202 experiment envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => copy() });
    vi.stubGlobal('fetch', fetchMock);
    const { createPairedExperiment, PAIRED_EXPERIMENTS_URL } = await import('./pairedExperiment');
    const created = await createPairedExperiment(createInput);
    expect(created.experiment_id).toBe('paired-exp-001');
    expect(fetchMock).toHaveBeenCalledWith(PAIRED_EXPERIMENTS_URL, expect.objectContaining({ method: 'POST', body: JSON.stringify(createInput) }));
    vi.unstubAllGlobals();
  });
  it('posts retry to the API retry route with the documented all-eligible-pairs body', async () => {
    const resumed = structuredClone(failedPairWithStaleDeltaFixture) as any; resumed.experiment.status = 'queued'; resumed.experiment.completed_pairs = 1; resumed.experiment.failed_pairs = 0; resumed.experiment.missing_pairs = 1; resumed.experiment.missing_pair_ids = ['pair-42']; resumed.experiment.pairs[1].status = 'queued'; resumed.experiment.pairs[1].executions.strategy.status = 'queued';
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => resumed });
    vi.stubGlobal('fetch', fetchMock);
    const { retryPairedExperiment, PAIRED_EXPERIMENTS_URL } = await import('./pairedExperiment');
    await expect(retryPairedExperiment('paired-exp-001')).resolves.toMatchObject({ status: 'queued', completed_pairs: 1, missing_pairs: 1 });
    expect(fetchMock).toHaveBeenCalledWith(`${PAIRED_EXPERIMENTS_URL}/paired-exp-001/retry`, expect.objectContaining({ method: 'POST', body: JSON.stringify({ pair_ids: null }) }));
    vi.unstubAllGlobals();
  });
  it('gets by encoded experiment ID and returns API detail errors', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, status: 200, json: async () => copy() }).mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({ detail: 'Experiment not found.' }) });
    vi.stubGlobal('fetch', fetchMock);
    const { fetchPairedExperiment, PAIRED_EXPERIMENTS_URL } = await import('./pairedExperiment');
    await expect(fetchPairedExperiment('paired-exp-001')).resolves.toMatchObject({ experiment_id: 'paired-exp-001' });
    expect(fetchMock.mock.calls[0][0]).toBe(`${PAIRED_EXPERIMENTS_URL}/paired-exp-001`);
    await expect(fetchPairedExperiment('missing')).rejects.toThrow('Experiment not found.');
    vi.unstubAllGlobals();
  });
});

describe('API JCS policy hashes', () => { it('matches the canonical baseline payload hash expected by the server', async () => { await expect(computePolicySha256('baseline', '1', null)).resolves.toBe('3f40e183a4a2c9a8d5ee534d7d7f12f21150ba7db32f7d1316a4310db5db5224'); }); });
