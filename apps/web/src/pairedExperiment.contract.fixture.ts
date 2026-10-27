const sha = 'a'.repeat(64);
const distribution = { mean: 0, sd: null, median: 0, iqr: null, min: 0, max: 0 };

export const pairedExperimentContractFixture = {
  experiment: {
    experiment_id: 'paired-exp-001', dto_schema_version: '1.0', protocol_id: 'aurora-paired-multiseed-v1', protocol_version: 1,
    manifest_sha256: sha, arena_manifest_id: 'arena-manifest-001', arena_manifest_sha256: sha,
    status: 'succeeded', planned_pairs: 1, completed_pairs: 1, failed_pairs: 0, running_pairs: 0, missing_pairs: 0, missing_pair_ids: [],
    limitations: ['synthetic_aurora', 'window_only', 'network_aggregated', 'not_causal', 'not_real_world_validated'],
    pairs: [{ pair_id: 'pair-001', strategy_id: 'signal_timing_node_02_04', baseline_execution_id: 'exec-base-001', strategy_execution_id: 'exec-strategy-001', window_id: 'weekday_am_peak', seed: 42, common_input_sha256: sha, status: 'succeeded',
      baseline_metrics: { trips_completed: { value: 0, unit: 'trips', period: 'completed_trips_through_drain', provenance_kind: 'simulated', method_version: 'sumo-metrics-v1', artifact_sha256: sha }, mean_queue_length_meters: { value: null, unit: 'm', period: 'demand_window', provenance_kind: 'simulated', method_version: 'sumo-metrics-v1', artifact_sha256: sha } },
      strategy_metrics: { trips_completed: { value: 0, unit: 'trips', period: 'completed_trips_through_drain', provenance_kind: 'simulated', method_version: 'sumo-metrics-v1', artifact_sha256: sha }, mean_queue_length_meters: { value: null, unit: 'm', period: 'demand_window', provenance_kind: 'simulated', method_version: 'sumo-metrics-v1', artifact_sha256: sha } },
      deltas: { trips_completed: { value: 0, unit: 'trips', direction: 'strategy_minus_baseline', provenance_kind: 'derived', method_version: 'summary-v1' } }, route_exposure: 'unknown',
      executions: { baseline: { execution_id: 'exec-base-001', status: 'succeeded', attempts: [{ attempt: 1, status: 'succeeded', error: null, artifact_sha256: sha }] }, strategy: { execution_id: 'exec-strategy-001', status: 'succeeded', attempts: [{ attempt: 1, status: 'succeeded', error: null, artifact_sha256: sha }] } } }],
    summaries_by_window: [{ window_id: 'weekday_am_peak', strategy_id: 'signal_timing_node_02_04', metric_id: 'trips_completed', unit: 'trips', period: 'completed_trips_through_drain', provenance_kind: 'derived', method_version: 'summary-v1', n_planned: 1, n_complete: 1, arm_summary: distribution, paired_delta_summary: distribution, confidence_interval: { method: 'student_t_paired', level: 0.95, lower: null, upper: null, n: 1, degrees_of_freedom: null, interpretation: 'conditional_monte_carlo_only', multiplicity: 'marginal_descriptive' } }],
  },
};

export const failedPairWithStaleDeltaFixture = {
  experiment: {
    ...pairedExperimentContractFixture.experiment,
    status: 'failed',
    completed_pairs: 0,
    failed_pairs: 1,
    pairs: pairedExperimentContractFixture.experiment.pairs.map((pair) => ({ ...pair, status: 'failed' })),
    summaries_by_window: pairedExperimentContractFixture.experiment.summaries_by_window.map((summary) => ({
      ...summary,
      n_complete: 0,
      paired_delta_summary: { mean: null, sd: null, median: null, iqr: null, min: null, max: null },
      confidence_interval: { ...summary.confidence_interval, lower: null, upper: null, n: 0, degrees_of_freedom: null },
    })),
  },
};
