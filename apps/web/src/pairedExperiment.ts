export type ExperimentStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled';
export type ExecutionStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type ProvenanceKind = 'synthetic_config' | 'synthetic_generated' | 'simulated' | 'derived';
export type MetricPeriod = 'demand_window' | 'completed_trips_through_drain';

export interface MetricValue {
  value: number | null;
  unit: string;
  period: MetricPeriod;
  provenance_kind: ProvenanceKind;
  method_version: string;
  artifact_sha256: string;
}

export interface DeltaValue {
  value: number | null;
  unit: string;
  direction: 'strategy_minus_baseline';
  provenance_kind: 'derived';
  method_version: string;
}

export interface ExperimentAttempt {
  attempt: number;
  status: ExecutionStatus;
  error: string | null;
  artifact_sha256: string | null;
}

export interface ExperimentPair {
  pair_id: string;
  strategy_id: string;
  baseline_execution_id: string;
  strategy_execution_id: string;
  window_id: string;
  seed: number;
  common_input_sha256: string;
  status: ExecutionStatus;
  baseline_metrics: Record<string, MetricValue> | null;
  strategy_metrics: Record<string, MetricValue> | null;
  deltas: Record<string, DeltaValue> | null;
  route_exposure: 'exposed' | 'not_exposed' | 'unknown';
  executions: {
    baseline: { execution_id: string; status: ExecutionStatus; attempts: ExperimentAttempt[] };
    strategy: { execution_id: string; status: ExecutionStatus; attempts: ExperimentAttempt[] };
  };
}

export interface DistributionSummary {
  mean: number | null;
  sd: number | null;
  median: number | null;
  iqr: number | null;
  min: number | null;
  max: number | null;
}

export interface ConfidenceInterval {
  method: string;
  level: number;
  lower: number | null;
  upper: number | null;
  n: number;
  degrees_of_freedom: number | null;
  interpretation: string;
  multiplicity: string;
}

export interface WindowSummary {
  window_id: string;
  strategy_id: string;
  metric_id: string;
  unit: string;
  period: MetricPeriod;
  provenance_kind: ProvenanceKind;
  method_version: string;
  n_planned: number;
  n_complete: number;
  arm_summary: DistributionSummary;
  paired_delta_summary: DistributionSummary;
  confidence_interval: ConfidenceInterval;
}

export interface PairedExperiment {
  experiment_id: string;
  dto_schema_version: '1.0';
  protocol_id: 'aurora-paired-multiseed-v1';
  protocol_version: 1;
  manifest_sha256: string;
  arena_manifest_id: string;
  arena_manifest_sha256: string;
  status: ExperimentStatus;
  planned_pairs: number;
  completed_pairs: number;
  failed_pairs: number;
  running_pairs: number;
  missing_pairs: number;
  missing_pair_ids: string[];
  limitations: string[];
  pairs: ExperimentPair[];
  summaries_by_window: WindowSummary[];
}

export interface CreateExperimentInput {
  arena_manifest_id: string;
  arena_manifest_sha256: string;
  round_index: number;
  instance_id: string;
  window_ids: string[];
  strategy_ids: string[];
  baseline_strategy_id: string;
  seeds: number[];
  seed_scope: 'sumo_operational_randomness';
  seed_selection_method: string;
  master_seed: number | null;
  primary_metric_ids: string[];
  secondary_metric_ids: string[];
  drain_limit_seconds: number;
  max_sumo_runs: number;
  max_attempts_per_execution: number;
  max_reproducibility_checks: number;
  max_wall_clock_seconds_per_run: number;
  max_total_wall_clock_seconds: number;
}

export type ExpectedExperimentPlan = Pick<CreateExperimentInput, 'window_ids' | 'strategy_ids' | 'seeds' | 'primary_metric_ids' | 'secondary_metric_ids'>;

// The specification fixes the response DTO but deliberately leaves endpoints and
// create-command fields open. Keep this provisional request boundary in one client
// module so the sibling API branch can align it without changing the v1.0 DTO parser.
export const PAIRED_EXPERIMENTS_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '') + '/api/v1/paired-multiseed-experiments';

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error(`DTO inválido: ${path} deve ser um objeto.`);
  return value as Record<string, unknown>;
}
function string(value: unknown, path: string): string {
  if (typeof value !== 'string' || value.length === 0) throw new Error(`DTO inválido: ${path} deve ser texto não vazio.`);
  return value;
}
function integer(value: unknown, path: string, minimum = 0): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) throw new Error(`DTO inválido: ${path} deve ser inteiro >= ${minimum}.`);
  return value as number;
}
function finiteOrNull(value: unknown, path: string): number | null {
  if (value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`DTO inválido: ${path} deve ser número finito ou null.`);
  return value;
}
function oneOf<T extends string>(value: unknown, choices: readonly T[], path: string): T {
  if (typeof value !== 'string' || !choices.includes(value as T)) throw new Error(`DTO inválido: ${path} não pertence ao contrato v1.0.`);
  return value as T;
}
function hash(value: unknown, path: string): string {
  const result = string(value, path);
  if (!/^[a-f0-9]{64}$/.test(result)) throw new Error(`DTO inválido: ${path} deve ser SHA-256 hexadecimal lowercase.`);
  return result;
}
const experimentStatuses = ['queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled'] as const;
const executionStatuses = ['queued', 'running', 'succeeded', 'failed', 'cancelled'] as const;
const provenanceKinds = ['synthetic_config', 'synthetic_generated', 'simulated', 'derived'] as const;
const periods = ['demand_window', 'completed_trips_through_drain'] as const;
const expectedPeriods: Record<string, MetricPeriod> = {
  mean_queue_length_meters: 'demand_window',
  mean_travel_time_seconds: 'completed_trips_through_drain',
  mean_speed_kmh: 'completed_trips_through_drain',
  trips_completed: 'completed_trips_through_drain',
  trips_not_completed: 'completed_trips_through_drain',
  trips_requested: 'demand_window',
};

function parseMetricMap(value: unknown, path: string, delta = false): Record<string, MetricValue> | Record<string, DeltaValue> | null {
  if (value === null) return null;
  const source = record(value, path);
  const parsed: Record<string, MetricValue | DeltaValue> = {};
  for (const [id, raw] of Object.entries(source)) {
    const metric = record(raw, `${path}.${id}`);
    if (delta) {
      if (metric.direction !== 'strategy_minus_baseline' || metric.provenance_kind !== 'derived') throw new Error(`DTO inválido: ${path}.${id} deve ser um delta derivado estratégia − baseline.`);
      parsed[id] = { value: finiteOrNull(metric.value, `${path}.${id}.value`), unit: string(metric.unit, `${path}.${id}.unit`), direction: 'strategy_minus_baseline', provenance_kind: 'derived', method_version: string(metric.method_version, `${path}.${id}.method_version`) };
    } else {
      const period = oneOf(metric.period, periods, `${path}.${id}.period`);
      if (expectedPeriods[id] && period !== expectedPeriods[id]) throw new Error(`DTO inválido: ${path}.${id}.period diverge da semântica temporal documentada.`);
      parsed[id] = { value: finiteOrNull(metric.value, `${path}.${id}.value`), unit: string(metric.unit, `${path}.${id}.unit`), period, provenance_kind: oneOf(metric.provenance_kind, provenanceKinds, `${path}.${id}.provenance_kind`), method_version: string(metric.method_version, `${path}.${id}.method_version`), artifact_sha256: hash(metric.artifact_sha256, `${path}.${id}.artifact_sha256`) };
    }
  }
  return parsed as Record<string, MetricValue> | Record<string, DeltaValue>;
}

function parseAttempts(value: unknown, path: string): ExperimentAttempt[] {
  if (!Array.isArray(value)) throw new Error(`DTO inválido: ${path} deve ser uma lista.`);
  const attempts = value.map((raw, index) => {
    const item = record(raw, `${path}[${index}]`);
    if (item.error !== null && typeof item.error !== 'string') throw new Error(`DTO inválido: ${path}[${index}].error deve ser texto ou null.`);
    return { attempt: integer(item.attempt, `${path}[${index}].attempt`, 1), status: oneOf(item.status, executionStatuses, `${path}[${index}].status`), error: item.error as string | null, artifact_sha256: item.artifact_sha256 === null ? null : hash(item.artifact_sha256, `${path}[${index}].artifact_sha256`) };
  });
  if (attempts.some((attempt, index) => attempt.attempt !== index + 1)) throw new Error(`DTO inválido: ${path} deve ter ordinais únicos, crescentes e iniciados em 1.`);
  return attempts;
}

function parsePair(value: unknown, index: number): ExperimentPair {
  const path = `experiment.pairs[${index}]`;
  const pair = record(value, path);
  const executions = record(pair.executions, `${path}.executions`);
  const parseExecution = (key: 'baseline' | 'strategy') => {
    const execution = record(executions[key], `${path}.executions.${key}`);
    const status = oneOf(execution.status, executionStatuses, `${path}.executions.${key}.status`);
    const attempts = parseAttempts(execution.attempts, `${path}.executions.${key}.attempts`);
    const finalAttemptStatus = attempts.at(-1)?.status;
    if (attempts.length && finalAttemptStatus !== status) throw new Error(`DTO inválido: ${path}.executions.${key} diverge do estado de sua tentativa mais recente.`);
    return { execution_id: string(execution.execution_id, `${path}.executions.${key}.execution_id`), status, attempts };
  };
  const status = oneOf(pair.status, executionStatuses, `${path}.status`);
  const baselineExecution = parseExecution('baseline');
  const strategyExecution = parseExecution('strategy');
  if (status === 'running' && baselineExecution.status !== 'running' && strategyExecution.status !== 'running') throw new Error(`DTO inválido: pair running precisa de ao menos um braço running.`);
  if (pair.baseline_execution_id !== baselineExecution.execution_id || pair.strategy_execution_id !== strategyExecution.execution_id) throw new Error(`DTO inválido: ${path} IDs planos e aninhados das execuções divergem.`);
  const baselineMetrics = parseMetricMap(pair.baseline_metrics, `${path}.baseline_metrics`) as Record<string, MetricValue> | null;
  const strategyMetrics = parseMetricMap(pair.strategy_metrics, `${path}.strategy_metrics`) as Record<string, MetricValue> | null;
  const reportedDeltas = parseMetricMap(pair.deltas, `${path}.deltas`, true) as Record<string, DeltaValue> | null;
  // A non-succeeded pair may retain completed-arm metrics, but it cannot
  // contribute a paired delta even when both arm executions succeeded.
  const deltas = status === 'succeeded' ? reportedDeltas : null;
  const armHasInvalidMetrics = (execution: typeof baselineExecution, metrics: Record<string, MetricValue> | null) => execution.status === 'succeeded' ? metrics === null : metrics !== null;
  if (armHasInvalidMetrics(baselineExecution, baselineMetrics) || armHasInvalidMetrics(strategyExecution, strategyMetrics)) throw new Error(`DTO inválido: cada braço concluído deve manter suas métricas; braços incompletos devem ter métricas null.`);
  if (status === 'succeeded' && (!baselineMetrics || !strategyMetrics || !deltas || baselineExecution.status !== 'succeeded' || strategyExecution.status !== 'succeeded')) throw new Error(`DTO inválido: ${path} bem-sucedido precisa dos dois braços concluídos e dos deltas.`);
  if (deltas !== null && (baselineExecution.status !== 'succeeded' || strategyExecution.status !== 'succeeded')) throw new Error(`DTO inválido: ${path} não pode expor delta sem sucesso nos dois braços.`);
  return { pair_id: string(pair.pair_id, `${path}.pair_id`), strategy_id: string(pair.strategy_id, `${path}.strategy_id`), baseline_execution_id: string(pair.baseline_execution_id, `${path}.baseline_execution_id`), strategy_execution_id: string(pair.strategy_execution_id, `${path}.strategy_execution_id`), window_id: string(pair.window_id, `${path}.window_id`), seed: integer(pair.seed, `${path}.seed`), common_input_sha256: hash(pair.common_input_sha256, `${path}.common_input_sha256`), status, baseline_metrics: baselineMetrics, strategy_metrics: strategyMetrics, deltas, route_exposure: oneOf(pair.route_exposure, ['exposed', 'not_exposed', 'unknown'] as const, `${path}.route_exposure`), executions: { baseline: baselineExecution, strategy: strategyExecution } };
}

export type PairOutcome = 'completed' | 'running' | 'failed' | 'missing';
export function pairOutcome(pair: ExperimentPair): PairOutcome {
  if (pair.status === 'succeeded') return 'completed';
  if (pair.status === 'running') return 'running';
  if (pair.status === 'failed' || pair.status === 'cancelled') return 'failed';
  return 'missing';
}

function parseDistribution(value: unknown, path: string): DistributionSummary {
  const summary = record(value, path);
  return { mean: finiteOrNull(summary.mean, `${path}.mean`), sd: finiteOrNull(summary.sd, `${path}.sd`), median: finiteOrNull(summary.median, `${path}.median`), iqr: finiteOrNull(summary.iqr, `${path}.iqr`), min: finiteOrNull(summary.min, `${path}.min`), max: finiteOrNull(summary.max, `${path}.max`) };
}
function parseWindowSummary(value: unknown, index: number): WindowSummary {
  const path = `experiment.summaries_by_window[${index}]`;
  const item = record(value, path);
  const ci = record(item.confidence_interval, `${path}.confidence_interval`);
  const method = string(ci.method, `${path}.confidence_interval.method`);
  if (method !== 'student_t_paired') throw new Error(`DTO inválido: ${path}.confidence_interval.method deve ser student_t_paired no método primário v1.`);
  const level = finiteOrNull(ci.level, `${path}.confidence_interval.level`);
  if (level !== 0.95) throw new Error(`DTO inválido: ${path}.confidence_interval.level deve ser 0.95.`);
  const n = integer(ci.n, `${path}.confidence_interval.n`);
  const df = finiteOrNull(ci.degrees_of_freedom, `${path}.confidence_interval.degrees_of_freedom`);
  const lower = finiteOrNull(ci.lower, `${path}.confidence_interval.lower`);
  const upper = finiteOrNull(ci.upper, `${path}.confidence_interval.upper`);
  const nPlanned = integer(item.n_planned, `${path}.n_planned`);
  const nComplete = integer(item.n_complete, `${path}.n_complete`);
  const metricId = string(item.metric_id, `${path}.metric_id`);
  const pairedDeltaSummary = parseDistribution(item.paired_delta_summary, `${path}.paired_delta_summary`);
  const period = oneOf(item.period, periods, `${path}.period`);
  const provenance = oneOf(item.provenance_kind, provenanceKinds, `${path}.provenance_kind`);
  if (expectedPeriods[metricId] && period !== expectedPeriods[metricId]) throw new Error(`DTO inválido: ${path}.period diverge da semântica temporal documentada para ${metricId}.`);
  if (provenance !== 'derived') throw new Error(`DTO inválido: ${path}.provenance_kind de resumo deve ser derived.`);
  if (nComplete === 0 && Object.values(pairedDeltaSummary).some((value) => value !== null)) throw new Error(`DTO inválido: ${path}.paired_delta_summary deve estar indisponível quando n_complete é zero.`);
  const intervalEligible = nComplete === nPlanned && n === nComplete;
  if (nComplete > nPlanned || n > nComplete || (!intervalEligible && (lower !== null || upper !== null || df !== null)) || (n < 2 && (lower !== null || upper !== null || df !== null)) || (intervalEligible && n >= 2 && (df !== n - 1 || lower === null || upper === null))) throw new Error(`DTO inválido: ${path}.confidence_interval é inconsistente com completude, n ou graus de liberdade.`);
  return { window_id: string(item.window_id, `${path}.window_id`), strategy_id: string(item.strategy_id, `${path}.strategy_id`), metric_id: metricId, unit: string(item.unit, `${path}.unit`), period, provenance_kind: provenance, method_version: string(item.method_version, `${path}.method_version`), n_planned: nPlanned, n_complete: nComplete, arm_summary: parseDistribution(item.arm_summary, `${path}.arm_summary`), paired_delta_summary: pairedDeltaSummary, confidence_interval: { method, level, lower, upper, n, degrees_of_freedom: df, interpretation: string(ci.interpretation, `${path}.confidence_interval.interpretation`), multiplicity: string(ci.multiplicity, `${path}.confidence_interval.multiplicity`) } };
}

export function parsePairedExperiment(value: unknown, expectedPlan?: ExpectedExperimentPlan): PairedExperiment {
  const envelope = record(value, 'response');
  const raw = record(envelope.experiment, 'response.experiment');
  if (raw.dto_schema_version !== '1.0' || raw.protocol_id !== 'aurora-paired-multiseed-v1' || raw.protocol_version !== 1) throw new Error('Contrato incompatível: esperado dto_schema_version 1.0 e aurora-paired-multiseed-v1/protocol_version 1.');
  if (!Array.isArray(raw.pairs) || !Array.isArray(raw.summaries_by_window) || !Array.isArray(raw.limitations)) throw new Error('DTO inválido: pairs, summaries_by_window e limitations devem ser listas.');
  const counts = ['planned_pairs', 'completed_pairs', 'failed_pairs', 'running_pairs', 'missing_pairs'] as const;
  const parsedCounts = Object.fromEntries(counts.map((key) => [key, integer(raw[key], `experiment.${key}`)])) as Record<(typeof counts)[number], number>;
  if (parsedCounts.planned_pairs !== parsedCounts.completed_pairs + parsedCounts.failed_pairs + parsedCounts.running_pairs + parsedCounts.missing_pairs) throw new Error('DTO inválido: contadores de pares não reconciliam.');
  const pairs = raw.pairs.map(parsePair);
  const status = oneOf(raw.status, experimentStatuses, 'experiment.status');
  if (!Array.isArray(raw.missing_pair_ids)) throw new Error('DTO inválido: missing_pair_ids deve ser uma lista.');
  if (pairs.length !== parsedCounts.planned_pairs) throw new Error('DTO inválido: pairs deve enumerar cada combinação planejada conforme o DTO da API.');
  const pairIds = new Set<string>();
  const cells = new Set<string>();
  for (const pair of pairs) {
    const cell = `${pair.strategy_id}\0${pair.window_id}\0${pair.seed}`;
    if (pairIds.has(pair.pair_id) || cells.has(cell)) throw new Error('DTO inválido: pairs contém identidade ou célula estratégia/janela/seed duplicada.');
    pairIds.add(pair.pair_id);
    cells.add(cell);
  }
  const includedCompleted = pairs.filter((pair) => pair.status === 'succeeded').length;
  const includedFailed = pairs.filter((pair) => pair.status === 'failed' || pair.status === 'cancelled').length;
  const includedRunning = pairs.filter((pair) => pair.status === 'running').length;
  const includedMissing = pairs.filter((pair) => pair.status === 'queued').length;
  const missingPairIds = raw.missing_pair_ids.map((id, index) => string(id, `experiment.missing_pair_ids[${index}]`));
  const expectedMissingIds = pairs.filter((pair) => pair.status === 'queued').map((pair) => pair.pair_id).sort();
  if (new Set(missingPairIds).size !== missingPairIds.length || [...missingPairIds].sort().some((id, index) => id !== expectedMissingIds[index]) || missingPairIds.length !== expectedMissingIds.length || missingPairIds.length !== parsedCounts.missing_pairs) throw new Error('DTO inválido: missing_pair_ids deve listar exatamente os pares queued e reconciliar missing_pairs.');
  if (includedCompleted !== parsedCounts.completed_pairs || includedFailed !== parsedCounts.failed_pairs || includedRunning !== parsedCounts.running_pairs || includedMissing !== parsedCounts.missing_pairs) throw new Error('DTO inválido: contadores agregados não correspondem aos estados dos pares enumerados.');
  const rowsAreComplete = true;
  const windows = new Set(pairs.map((pair) => pair.window_id));
  const strategies = new Set(pairs.map((pair) => pair.strategy_id));
  const seeds = new Set(pairs.map((pair) => pair.seed));
  const plannedCardinality = windows.size * strategies.size * seeds.size;
  if (plannedCardinality > parsedCounts.planned_pairs || (rowsAreComplete && plannedCardinality !== parsedCounts.planned_pairs)) throw new Error('DTO inválido: cardinalidade de estratégia × janela × seed contradiz planned_pairs.');
  if (expectedPlan) {
    const expectedCells = new Set(expectedPlan.strategy_ids.flatMap((strategy) => expectedPlan.window_ids.flatMap((windowId) => expectedPlan.seeds.map((seed) => `${strategy}\0${windowId}\0${seed}`))));
    if (expectedCells.size !== parsedCounts.planned_pairs || expectedCells.size !== cells.size || [...expectedCells].some((cell) => !cells.has(cell))) throw new Error('DTO inválido: pares retornados não correspondem às estratégias, janelas e seeds explicitamente solicitadas.');
    if (pairs.some((pair) => !expectedPlan.window_ids.includes(pair.window_id) || !expectedPlan.strategy_ids.includes(pair.strategy_id))) throw new Error('DTO inválido: par retornado usa janela ou estratégia fora do plano solicitado.');
  }
  if (status === 'succeeded' && pairs.some((pair) => pairOutcome(pair) !== 'completed')) throw new Error('DTO inválido: experimento succeeded contém par retornado que não foi concluído.');
  if (status === 'succeeded' && parsedCounts.missing_pairs + parsedCounts.failed_pairs + parsedCounts.running_pairs !== 0) throw new Error('DTO inválido: experimento succeeded possui pares pendentes ou inválidos.');
  if (status === 'queued' && parsedCounts.completed_pairs + parsedCounts.failed_pairs + parsedCounts.running_pairs !== 0) throw new Error('DTO inválido: experimento queued já contém pares executados ou inválidos.');
  if (status === 'partial' && (parsedCounts.running_pairs !== 0 || parsedCounts.completed_pairs === parsedCounts.planned_pairs)) throw new Error('DTO inválido: experimento partial deve estar sem pares ativos e com plano incompleto.');
  if (status === 'failed' && parsedCounts.running_pairs !== 0) throw new Error('DTO inválido: experimento failed não pode manter pares em execução.');
  if (status === 'cancelled' && parsedCounts.running_pairs !== 0) throw new Error('DTO inválido: experimento cancelled não pode manter pares em execução.');
  const summaries = raw.summaries_by_window.map(parseWindowSummary);
  const plannedByWindowStrategy = new Map<string, number>();
  const completedByWindowStrategy = new Map<string, number>();
  const metricCompleteByKey = new Map<string, number>();
  for (const pair of pairs) {
    const key = `${pair.window_id}\0${pair.strategy_id}`;
    plannedByWindowStrategy.set(key, (plannedByWindowStrategy.get(key) ?? 0) + 1);
    if (pairOutcome(pair) === 'completed') completedByWindowStrategy.set(key, (completedByWindowStrategy.get(key) ?? 0) + 1);
    for (const [metricId, delta] of Object.entries(pair.deltas ?? {})) {
      if (delta.value !== null) {
        const metricKey = `${key}\0${metricId}`;
        metricCompleteByKey.set(metricKey, (metricCompleteByKey.get(metricKey) ?? 0) + 1);
      }
    }
  }
  for (const summary of summaries) {
    const key = `${summary.window_id}\0${summary.strategy_id}`;
    const observedPlanned = plannedByWindowStrategy.get(key) ?? 0;
    if (!windows.has(summary.window_id) || !strategies.has(summary.strategy_id)) throw new Error('DTO inválido: resumo referencia janela ou estratégia fora do plano solicitado e sem pares planejados.');
    const expectedCount = expectedPlan && expectedPlan.window_ids.includes(summary.window_id) && expectedPlan.strategy_ids.includes(summary.strategy_id) ? expectedPlan.seeds.length : undefined;
    if (expectedPlan && (expectedCount === undefined || ![...expectedPlan.primary_metric_ids, ...expectedPlan.secondary_metric_ids].includes(summary.metric_id))) throw new Error('DTO inválido: resumo inclui janela, estratégia ou métrica fora do plano solicitado.');
    const completeCountUpperBound = rowsAreComplete ? (completedByWindowStrategy.get(key) ?? 0) : parsedCounts.completed_pairs;
    const metricKey = `${key}\0${summary.metric_id}`;
    const observedMetricComplete = metricCompleteByKey.get(metricKey) ?? 0;
    if ((expectedCount !== undefined && summary.n_planned !== expectedCount) || (rowsAreComplete && summary.n_planned !== observedPlanned) || (!rowsAreComplete && summary.n_planned < observedPlanned) || summary.n_complete > completeCountUpperBound || (rowsAreComplete && summary.n_complete !== observedMetricComplete) || (!rowsAreComplete && summary.n_complete < observedMetricComplete)) throw new Error('DTO inválido: contagens do resumo não correspondem às combinações observáveis e deltas disponíveis de sua janela/estratégia/métrica.');
  }
  const keys = new Set<string>();
  for (const summary of summaries) {
    const key = `${summary.window_id}\0${summary.strategy_id}\0${summary.metric_id}`;
    if (keys.has(key)) throw new Error('DTO inválido: summaries_by_window contém duplicata de janela/estratégia/métrica.');
    keys.add(key);
  }
  return { experiment_id: string(raw.experiment_id, 'experiment.experiment_id'), dto_schema_version: '1.0', protocol_id: 'aurora-paired-multiseed-v1', protocol_version: 1, manifest_sha256: hash(raw.manifest_sha256, 'experiment.manifest_sha256'), arena_manifest_id: string(raw.arena_manifest_id, 'experiment.arena_manifest_id'), arena_manifest_sha256: hash(raw.arena_manifest_sha256, 'experiment.arena_manifest_sha256'), status, ...parsedCounts, missing_pair_ids: missingPairIds, limitations: raw.limitations.map((item, index) => string(item, `experiment.limitations[${index}]`)), pairs, summaries_by_window: summaries };
}

async function requestJson(url: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(url, { ...init, headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init.headers } });
  if (!response.ok) throw new Error(`A API respondeu com erro HTTP ${response.status}.`);
  try { return await response.json() as unknown; } catch { throw new Error('A API retornou uma resposta que não é JSON válido.'); }
}

export async function createPairedExperiment(input: CreateExperimentInput): Promise<PairedExperiment> {
  return parsePairedExperiment(await requestJson(PAIRED_EXPERIMENTS_URL, { method: 'POST', body: JSON.stringify(input) }), input);
}
export async function fetchPairedExperiment(id: string, signal?: AbortSignal, expectedPlan?: ExpectedExperimentPlan): Promise<PairedExperiment> {
  const result = parsePairedExperiment(await requestJson(`${PAIRED_EXPERIMENTS_URL}/${encodeURIComponent(id)}`, { method: 'GET', signal }), expectedPlan);
  if (result.experiment_id !== id) throw new Error('A API retornou outro experimento durante o acompanhamento.');
  return result;
}
