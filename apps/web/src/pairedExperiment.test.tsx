import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MetricProvenanceCell, PairedExperimentPanel } from './PairedExperimentPanel';
import { parsePairedExperiment } from './pairedExperiment';
import { failedPairWithStaleDeltaFixture, pairedExperimentContractFixture } from './pairedExperiment.contract.fixture';

const copy = (): { experiment: Record<string, any> } => structuredClone(pairedExperimentContractFixture) as { experiment: Record<string, any> };

describe('paired multi-seed DTO v1.0 adapter', () => {
  it('accepts the documented envelope, keeps zero distinct from unavailable and retains provenance and period', () => {
    const parsed = parsePairedExperiment(copy());
    expect(parsed.dto_schema_version).toBe('1.0');
    expect(parsed.pairs[0].baseline_metrics?.trips_completed.value).toBe(0);
    expect(parsed.pairs[0].baseline_metrics?.mean_queue_length_meters.value).toBeNull();
    expect(parsed.pairs[0].route_exposure).toBe('unknown');
    expect(parsed.pairs[0].strategy_metrics?.trips_completed.period).toBe('completed_trips_through_drain');
    expect(parsed.pairs[0].strategy_metrics?.trips_completed.provenance_kind).toBe('simulated');
    expect(parsed.summaries_by_window[0].confidence_interval.n).toBe(1);
    expect(() => parsePairedExperiment(copy(), { window_ids: ['weekday_off_peak'], strategy_ids: ['signal_timing_node_02_04'], seeds: [42], primary_metric_ids: ['trips_completed'], secondary_metric_ids: [] })).toThrow(/não correspondem às estratégias, janelas e seeds explicitamente solicitadas/);
  });

  it('rejects a different schema/protocol version and non-reconciling pair counts', () => {
    const wrongVersion = copy();
    wrongVersion.experiment.dto_schema_version = '2.0';
    expect(() => parsePairedExperiment(wrongVersion)).toThrow(/dto_schema_version/);
    const wrongCounts = copy();
    wrongCounts.experiment.missing_pairs = 1;
    expect(() => parsePairedExperiment(wrongCounts)).toThrow(/não reconciliam/);
  });

  it('rejects malformed hashes, duplicate cells, identity mismatches, and partial metrics on failed pairs', () => {
    const badHash = copy();
    badHash.experiment.manifest_sha256 = 'not-a-sha';
    expect(() => parsePairedExperiment(badHash)).toThrow(/SHA-256/);
    const duplicate = copy();
    duplicate.experiment.pairs.push(structuredClone(duplicate.experiment.pairs[0]));
    duplicate.experiment.planned_pairs = 2;
    duplicate.experiment.completed_pairs = 2;
    expect(() => parsePairedExperiment(duplicate)).toThrow(/duplicada/);
    const mismatchedExecution = copy();
    mismatchedExecution.experiment.pairs[0].executions.baseline.execution_id = 'different-id';
    expect(() => parsePairedExperiment(mismatchedExecution)).toThrow(/IDs planos e aninhados/);
    const partialMetrics = copy();
    partialMetrics.experiment.pairs[0].status = 'failed';
    partialMetrics.experiment.pairs[0].strategy_metrics = null;
    partialMetrics.experiment.pairs[0].deltas = null;
    expect(() => parsePairedExperiment(partialMetrics)).toThrow(/braços incompletos devem ter métricas null/);
  });

  it('rejects invalid attempt ordering and summaries with conflicting period or provenance', () => {
    const badAttempts = copy();
    badAttempts.experiment.pairs[0].executions.baseline.attempts.push({ attempt: 3, status: 'succeeded', error: null, artifact_sha256: 'a'.repeat(64) });
    expect(() => parsePairedExperiment(badAttempts)).toThrow(/ordinais únicos/);
    const badPeriod = copy();
    badPeriod.experiment.summaries_by_window[0].metric_id = 'mean_queue_length_meters';
    badPeriod.experiment.summaries_by_window[0].period = 'completed_trips_through_drain';
    expect(() => parsePairedExperiment(badPeriod)).toThrow(/semântica temporal/);
    const badProvenance = copy();
    badProvenance.experiment.summaries_by_window[0].provenance_kind = 'simulated';
    expect(() => parsePairedExperiment(badProvenance)).toThrow(/de resumo deve ser derived/);
  });

  it('preserves a successful arm on a failed pair and rejects an interval that omits planned pairs', () => {
    const failedPair = copy();
    failedPair.experiment.status = 'failed';
    failedPair.experiment.completed_pairs = 0;
    failedPair.experiment.failed_pairs = 1;
    failedPair.experiment.pairs[0].status = 'failed';
    failedPair.experiment.pairs[0].strategy_metrics = null;
    failedPair.experiment.pairs[0].deltas = null;
    failedPair.experiment.pairs[0].executions.strategy.status = 'failed';
    failedPair.experiment.pairs[0].executions.strategy.attempts[0].status = 'failed';
    failedPair.experiment.summaries_by_window[0].n_complete = 0;
    failedPair.experiment.summaries_by_window[0].arm_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    failedPair.experiment.summaries_by_window[0].paired_delta_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    failedPair.experiment.summaries_by_window[0].confidence_interval.n = 0;
    const parsed = parsePairedExperiment(failedPair);
    expect(parsed.pairs[0].baseline_metrics?.trips_completed.value).toBe(0);
    expect(parsed.pairs[0].strategy_metrics).toBeNull();
    expect(parsed.pairs[0].deltas).toBeNull();

    const cancelledPair = copy();
    cancelledPair.experiment.status = 'cancelled';
    cancelledPair.experiment.completed_pairs = 0;
    cancelledPair.experiment.failed_pairs = 1;
    cancelledPair.experiment.pairs[0].status = 'cancelled';
    cancelledPair.experiment.pairs[0].strategy_metrics = null;
    cancelledPair.experiment.pairs[0].deltas = null;
    cancelledPair.experiment.pairs[0].executions.strategy.status = 'cancelled';
    cancelledPair.experiment.pairs[0].executions.strategy.attempts[0].status = 'cancelled';
    cancelledPair.experiment.summaries_by_window[0].n_complete = 0;
    cancelledPair.experiment.summaries_by_window[0].arm_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    cancelledPair.experiment.summaries_by_window[0].paired_delta_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    cancelledPair.experiment.summaries_by_window[0].confidence_interval.n = 0;
    expect(parsePairedExperiment(cancelledPair).failed_pairs).toBe(1);

    const incompleteInterval = copy();
    incompleteInterval.experiment.summaries_by_window[0].confidence_interval = { method: 'student_t_paired', level: 0.95, lower: -1, upper: 1, n: 0, degrees_of_freedom: null, interpretation: 'conditional_monte_carlo_only', multiplicity: 'marginal_descriptive' };
    expect(() => parsePairedExperiment(incompleteInterval)).toThrow(/confidence_interval é inconsistente com completude/);
  });

  it('suppresses deltas from a failed pair even when both arms succeeded', () => {
    const failedPair = structuredClone(failedPairWithStaleDeltaFixture) as { experiment: Record<string, any> };
    const parsed = parsePairedExperiment(failedPair);
    expect(parsed.pairs[0].baseline_metrics?.trips_completed.value).toBe(0);
    expect(parsed.pairs[0].strategy_metrics?.trips_completed.value).toBe(0);
    expect(parsed.pairs[0].deltas).toBeNull();

    failedPair.experiment.summaries_by_window[0].paired_delta_summary.mean = 0;
    expect(() => parsePairedExperiment(failedPair)).toThrow(/paired_delta_summary deve estar indisponível quando n_complete é zero/);
  });

  it('rejects a successful experiment whose included pair contradicts its terminal status', () => {
    const inconsistent = copy();
    inconsistent.experiment.pairs[0].status = 'failed';
    inconsistent.experiment.pairs[0].baseline_metrics = null;
    inconsistent.experiment.pairs[0].strategy_metrics = null;
    inconsistent.experiment.pairs[0].deltas = null;
    inconsistent.experiment.pairs[0].executions.baseline.status = 'failed';
    inconsistent.experiment.pairs[0].executions.baseline.attempts[0].status = 'failed';
    inconsistent.experiment.pairs[0].executions.strategy.status = 'failed';
    inconsistent.experiment.pairs[0].executions.strategy.attempts[0].status = 'failed';
    inconsistent.experiment.completed_pairs = 0;
    inconsistent.experiment.failed_pairs = 1;
    expect(() => parsePairedExperiment(inconsistent)).toThrow(/experimento succeeded contém par retornado que não foi concluído/);
  });

  it('requires every planned cell and reconciles row states with global and window-strategy counts', () => {
    const omitted = copy();
    omitted.experiment.pairs = [];
    expect(() => parsePairedExperiment(omitted)).toThrow(/pairs deve enumerar cada combinação planejada/);
    expect(() => parsePairedExperiment(omitted, { window_ids: ['weekday_am_peak'], strategy_ids: ['signal_timing_node_02_04'], seeds: [42], primary_metric_ids: ['trips_completed'], secondary_metric_ids: [] })).toThrow(/pairs deve enumerar cada combinação planejada/);

    const rowCountMismatch = copy();
    rowCountMismatch.experiment.pairs[0].status = 'failed';
    rowCountMismatch.experiment.pairs[0].baseline_metrics = null;
    rowCountMismatch.experiment.pairs[0].strategy_metrics = null;
    rowCountMismatch.experiment.pairs[0].deltas = null;
    rowCountMismatch.experiment.pairs[0].executions.baseline.status = 'failed';
    rowCountMismatch.experiment.pairs[0].executions.baseline.attempts[0].status = 'failed';
    rowCountMismatch.experiment.pairs[0].executions.strategy.status = 'failed';
    rowCountMismatch.experiment.pairs[0].executions.strategy.attempts[0].status = 'failed';
    expect(() => parsePairedExperiment(rowCountMismatch)).toThrow(/contadores agregados não correspondem/);

    const queuedMismatch = copy();
    queuedMismatch.experiment.status = 'queued';
    expect(() => parsePairedExperiment(queuedMismatch)).toThrow(/experimento queued já contém pares executados/);

    const partialMismatch = copy();
    partialMismatch.experiment.status = 'partial';
    partialMismatch.experiment.completed_pairs = 0;
    partialMismatch.experiment.running_pairs = 1;
    partialMismatch.experiment.pairs[0].status = 'running';
    partialMismatch.experiment.pairs[0].baseline_metrics = null;
    partialMismatch.experiment.pairs[0].strategy_metrics = null;
    partialMismatch.experiment.pairs[0].deltas = null;
    for (const arm of ['baseline', 'strategy'] as const) {
      partialMismatch.experiment.pairs[0].executions[arm].status = 'running';
      partialMismatch.experiment.pairs[0].executions[arm].attempts[0].status = 'running';
    }
    expect(() => parsePairedExperiment(partialMismatch)).toThrow(/partial deve estar sem pares ativos/);

    const understatedSummary = copy();
    understatedSummary.experiment.summaries_by_window[0].n_complete = 0;
    understatedSummary.experiment.summaries_by_window[0].confidence_interval.n = 0;
    expect(() => parsePairedExperiment(understatedSummary)).toThrow(/paired_delta_summary deve estar indisponível/);

    const outsidePlan = copy();
    outsidePlan.experiment.summaries_by_window[0].window_id = 'weekday_off_peak';
    expect(() => parsePairedExperiment(outsidePlan, { window_ids: ['weekday_am_peak'], strategy_ids: ['signal_timing_node_02_04'], seeds: [42], primary_metric_ids: ['trips_completed'], secondary_metric_ids: [] })).toThrow(/fora do plano solicitado/);

    const ghostWindowSummary = copy();
    ghostWindowSummary.experiment.summaries_by_window[0].window_id = 'weekday_off_peak';
    ghostWindowSummary.experiment.summaries_by_window[0].n_planned = 0;
    ghostWindowSummary.experiment.summaries_by_window[0].n_complete = 0;
    ghostWindowSummary.experiment.summaries_by_window[0].paired_delta_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    ghostWindowSummary.experiment.summaries_by_window[0].confidence_interval.n = 0;
    expect(() => parsePairedExperiment(ghostWindowSummary)).toThrow(/sem pares planejados/);

    const ghostStrategySummary = copy();
    ghostStrategySummary.experiment.summaries_by_window[0].strategy_id = 'unplanned_strategy';
    ghostStrategySummary.experiment.summaries_by_window[0].n_planned = 0;
    ghostStrategySummary.experiment.summaries_by_window[0].n_complete = 0;
    ghostStrategySummary.experiment.summaries_by_window[0].paired_delta_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    ghostStrategySummary.experiment.summaries_by_window[0].confidence_interval.n = 0;
    expect(() => parsePairedExperiment(ghostStrategySummary)).toThrow(/sem pares planejados/);

    const betweenCells = copy();
    betweenCells.experiment.status = 'running';
    betweenCells.experiment.completed_pairs = 0;
    betweenCells.experiment.missing_pairs = 1;
    betweenCells.experiment.missing_pair_ids = ['pair-001'];
    betweenCells.experiment.pairs[0].status = 'queued';
    betweenCells.experiment.pairs[0].baseline_metrics = null;
    betweenCells.experiment.pairs[0].strategy_metrics = null;
    betweenCells.experiment.pairs[0].deltas = null;
    for (const arm of ['baseline', 'strategy'] as const) {
      betweenCells.experiment.pairs[0].executions[arm].status = 'queued';
      betweenCells.experiment.pairs[0].executions[arm].attempts[0].status = 'queued';
    }
    betweenCells.experiment.summaries_by_window[0].n_complete = 0;
    betweenCells.experiment.summaries_by_window[0].arm_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    betweenCells.experiment.summaries_by_window[0].paired_delta_summary = { mean: null, sd: null, median: null, iqr: null, min: null, max: null };
    betweenCells.experiment.summaries_by_window[0].confidence_interval.n = 0;
    expect(parsePairedExperiment(betweenCells).status).toBe('running');
    betweenCells.experiment.missing_pair_ids = [];
    expect(() => parsePairedExperiment(betweenCells)).toThrow(/missing_pair_ids deve listar exatamente/);

    const pairRunningWithoutArm = copy();
    pairRunningWithoutArm.experiment.status = 'running';
    pairRunningWithoutArm.experiment.completed_pairs = 0;
    pairRunningWithoutArm.experiment.running_pairs = 1;
    pairRunningWithoutArm.experiment.missing_pairs = 0;
    pairRunningWithoutArm.experiment.missing_pair_ids = [];
    pairRunningWithoutArm.experiment.pairs[0].status = 'running';
    pairRunningWithoutArm.experiment.pairs[0].baseline_metrics = null;
    pairRunningWithoutArm.experiment.pairs[0].strategy_metrics = null;
    pairRunningWithoutArm.experiment.pairs[0].deltas = null;
    for (const arm of ['baseline', 'strategy'] as const) {
      pairRunningWithoutArm.experiment.pairs[0].executions[arm].status = 'queued';
      pairRunningWithoutArm.experiment.pairs[0].executions[arm].attempts[0].status = 'queued';
    }
    expect(() => parsePairedExperiment(pairRunningWithoutArm)).toThrow(/pair running precisa de ao menos um braço running/);
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
