const hash = (char: string) => char.repeat(64);

const manifest = {
  arena_manifest_id: 'arena-manifest-001', arena_manifest_sha256: hash('a'), round_index: 1,
  instance_id: 'aurora-instance-001', city_id: 'aurora-base-v1',
  window_ids: ['weekday_am_peak'], seeds: [41, 42],
  strategies: [{ strategy_id: 'signal_timing_node_02_04', policy_version: '1', policy_sha256: hash('b'),
    intervention: { node_id: 'node_02_04', phases: [{ movement: 'north_south', duration_seconds: 30 }, { movement: 'east_west', duration_seconds: 30 }] } }],
  baseline_id: 'aurora-default', baseline_version: '1', baseline_sha256: hash('c'), drain_limit_seconds: 300,
  metrics: ['trips_completed', 'mean_queue_length_meters'],
  metric_tolerances: { trips_completed: { exact: true }, mean_queue_length_meters: { absolute: 0, relative: 0 } },
  method_version: 'sumo-metrics-v1',
  budget: { max_sumo_runs: 4, max_attempts_per_execution: 2, max_reproducibility_checks: 0, max_wall_clock_seconds_per_run: 60, max_total_wall_clock_seconds: 240, admit_incomplete: true },
  reproducibility_checks: 0, selection_method: 'externally_predeclared', master_seed: 9001,
  primary_metrics: ['trips_completed'], confidence_level: 0.95,
  limitations: ['synthetic_aurora', 'window_only', 'network_aggregated', 'not_causal', 'not_real_world_validated'],
};

const metric = (value: number | null, unit: string, period: string, artifact: string) => ({
  value, unit, period, provenance_kind: 'simulated', method_version: 'sumo-metrics-v1', artifact_sha256: artifact,
});

function pair(seed: number, index: number) {
  const baseHash = hash(index === 0 ? 'd' : 'e');
  const strategyHash = hash(index === 0 ? 'f' : '1');
  const commonHash = hash(index === 0 ? '2' : '3');
  const baselineId = `exec-base-${seed}`;
  const strategyId = `exec-strategy-${seed}`;
  const arm = (executionId: string, artifact: string, armHash: string) => ({
    execution_id: executionId, status: 'succeeded',
    attempts: [{ attempt: 1, status: 'succeeded', error: null, artifact_sha256: artifact, started_at: null, finished_at: null,
      wall_clock_seconds: 0, artifacts: {}, seed, window_id: 'weekday_am_peak', common_input_sha256: commonHash,
      arm_input_sha256: armHash, sumo_engine: 'sumo', sumo_version: '1.20.0' }],
    result_metrics: { trips_completed: 0, mean_queue_length_meters: null }, engine_version: 'sumo-1.20.0',
    metric_methods: { trips_completed: 'sumo-metrics-v1', mean_queue_length_meters: 'sumo-metrics-v1' },
    artifact_sha256: artifact, artifacts: {}, result_identity: null, seed, window_id: 'weekday_am_peak',
    common_input_sha256: commonHash, arm_input_sha256: armHash,
  });
  return {
    pair_id: `pair-${seed}`, strategy_id: 'signal_timing_node_02_04', baseline_execution_id: baselineId,
    strategy_execution_id: strategyId, window_id: 'weekday_am_peak', seed, common_input_sha256: commonHash,
    baseline_arm_input_sha256: baseHash, strategy_arm_input_sha256: strategyHash, status: 'succeeded',
    baseline_metrics: { trips_completed: metric(0, 'trips', 'completed_trips_through_drain', baseHash), mean_queue_length_meters: metric(null, 'meters', 'demand_window', baseHash) },
    strategy_metrics: { trips_completed: metric(0, 'trips', 'completed_trips_through_drain', strategyHash), mean_queue_length_meters: metric(null, 'meters', 'demand_window', strategyHash) },
    deltas: {
      trips_completed: { value: 0, unit: 'trips', direction: 'strategy_minus_baseline', provenance_kind: 'derived', method_version: 'paired-delta-v1', source_artifact_sha256: [baseHash, strategyHash] },
      mean_queue_length_meters: { value: null, unit: 'm', direction: 'strategy_minus_baseline', provenance_kind: 'derived', method_version: 'paired-delta-v1', source_artifact_sha256: [baseHash, strategyHash] },
    },
    route_exposure: 'unknown', error: null, artifact_files: {},
    executions: { baseline: arm(baselineId, baseHash, baseHash), strategy: arm(strategyId, strategyHash, strategyHash) },
  };
}

const pairs = [pair(41, 0), pair(42, 1)];
const summaries = ['trips_completed', 'mean_queue_length_meters'].map((metricId) => ({
  window_id: 'weekday_am_peak', strategy_id: 'signal_timing_node_02_04', metric_id: metricId,
  unit: metricId === 'trips_completed' ? 'trips' : 'm',
  period: metricId === 'trips_completed' ? 'completed_trips_through_drain' : 'demand_window',
  provenance_kind: 'derived', method_version: 'summary-student-t-v1', n_planned: 2, n_complete: metricId === 'trips_completed' ? 2 : 0,
  arm_summary: { baseline: { mean: 0, sd: 0, median: 0, iqr: 0, min: 0, max: 0 }, strategy: { mean: 0, sd: 0, median: 0, iqr: 0, min: 0, max: 0 } },
  paired_delta_summary: { mean: metricId === 'trips_completed' ? 0 : null, sd: metricId === 'trips_completed' ? 0 : null, median: metricId === 'trips_completed' ? 0 : null, iqr: metricId === 'trips_completed' ? 0 : null, min: metricId === 'trips_completed' ? 0 : null, max: metricId === 'trips_completed' ? 0 : null },
  confidence_interval: { method: 'student_t_paired', level: 0.95, lower: metricId === 'trips_completed' ? 0 : null, upper: metricId === 'trips_completed' ? 0 : null, n: metricId === 'trips_completed' ? 2 : 0, degrees_of_freedom: metricId === 'trips_completed' ? 1 : null, interpretation: 'conditional_monte_carlo_only', multiplicity: 'marginal_descriptive' },
  selection: 'complete_pairs_only', seed_sensitivity: 'no_variation_observed', arm_seed_sensitivity: 'no_variation_observed', paired_delta_seed_sensitivity: 'no_variation_observed',
}));

export const pairedExperimentContractFixture = {
  experiment: {
    experiment_id: 'paired-exp-001', dto_schema_version: '1.0', protocol_id: 'aurora-paired-multiseed-v1', protocol_version: 1,
    manifest_sha256: hash('4'), arena_manifest_id: 'arena-manifest-001', arena_manifest_sha256: hash('a'),
    status: 'succeeded', cancellation_requested: false,
    planned_pairs: 2, completed_pairs: 2, failed_pairs: 0, running_pairs: 0, missing_pairs: 0, missing_pair_ids: [],
    planned_executions: 4, attempts: 4, sumo_runs_used: 4, wall_clock_seconds_used: 0, reserved_wall_clock_seconds: 0,
    stop_reason: null, error_code: null, limitations: manifest.limitations, manifest, pairs, summaries_by_window: summaries,
  },
};

export const failedPairWithStaleDeltaFixture = {
  experiment: {
    ...pairedExperimentContractFixture.experiment,
    status: 'partial', completed_pairs: 1, failed_pairs: 1,
    pairs: [pairs[0], { ...pairs[1], status: 'failed', baseline_metrics: {}, strategy_metrics: {}, deltas: {},
      executions: { baseline: { ...pairs[1].executions.baseline, status: 'succeeded' }, strategy: { ...pairs[1].executions.strategy, status: 'failed', attempts: [{ ...pairs[1].executions.strategy.attempts[0], status: 'failed' }] } } }],
    summaries_by_window: summaries.map((summary) => ({ ...summary, n_complete: summary.metric_id === 'trips_completed' ? 1 : 0, confidence_interval: { ...summary.confidence_interval, n: summary.metric_id === 'trips_completed' ? 1 : 0, degrees_of_freedom: null, lower: null, upper: null } })),
  },
};
