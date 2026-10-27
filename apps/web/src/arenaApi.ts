/** Validated HTTP DTOs for the synthetic Aurora arena API. */

export type ArenaStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export type ArenaJsonValue = string | number | boolean | null | ArenaJsonValue[] | { [key: string]: ArenaJsonValue };
export type ArenaJsonObject = { [key: string]: ArenaJsonValue };

export interface ArenaIndicatorDTO {
  indicator_id: string;
  value: number | null;
  null_reason: string | null;
  unit: string;
  unit_basis: string;
  period: string;
  period_type: string;
  territory: string;
  coverage: { status: string; spatial: string; temporal: string; numerator: number | null; denominator: number | null; filters: string[] };
  [key: string]: ArenaJsonValue;
}

export interface ArenaRoundInstanceDTO {
  instance_id: string;
  indicators: ArenaIndicatorDTO[];
  proposal: ArenaJsonObject;
  decision: ArenaJsonObject;
  [key: string]: ArenaJsonValue;
}

export interface ArenaRoundDTO {
  round_index: number;
  instances: ArenaRoundInstanceDTO[];
}

export interface ArenaInstanceDTO {
  experiment_id: string;
  instance_id: string;
  agent_id: string;
  policy_id: string;
  policy_version: string;
  initial_city_state_hash: string;
  current_city_state_hash: string;
  current_round_index: number;
  current_state: ArenaJsonObject | null;
}

export interface ArenaJobDTO {
  arena_id: string;
  status: ArenaStatus;
  city_id: 'aurora-base-v1';
  provenance: 'synthetic';
  experiment_id: string;
  snapshot_id: string;
  snapshot_hash: string;
  manifest_hash: string;
  manifest: ArenaJsonObject & { horizon_rounds: number; provenance: 'synthetic_config' };
  horizon_rounds: number;
  committed_rounds: number;
  completed_rounds: number;
  instances: ArenaInstanceDTO[];
  rounds: ArenaRoundDTO[];
  error: ArenaJsonObject | null;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const CITY_ID = 'aurora-base-v1';
const INSTANCE_COUNT = 5;
const STATUSES: ArenaStatus[] = ['queued', 'running', 'succeeded', 'failed'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function contractError(detail: string): Error {
  return new Error(`Resposta inválida da API: ${detail}.`);
}

function requireString(value: unknown, field: string): asserts value is string {
  if (typeof value !== 'string') throw contractError(`campo ${field} ausente ou inválido`);
}

function requireInteger(value: unknown, field: string, min: number, max: number): asserts value is number {
  if (!Number.isInteger(value) || (value as number) < min || (value as number) > max) {
    throw contractError(`campo ${field} deve ser um inteiro entre ${min} e ${max}`);
  }
}

function requireNullableNumber(value: unknown, field: string): void {
  if (value !== null && (typeof value !== 'number' || !Number.isFinite(value))) {
    throw contractError(`campo ${field} deve ser número ou null`);
  }
}

function requireStringArray(value: unknown, field: string): void {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) throw contractError(`${field} deve conter strings`);
}

function requireNumberMap(value: unknown, field: string, integers = false): void {
  if (!isRecord(value) || !Object.values(value).every((item) => typeof item === 'number' && Number.isFinite(item) && (!integers || Number.isInteger(item)))) {
    throw contractError(`${field} deve mapear valores numéricos`);
  }
}

function validateCityState(state: Record<string, unknown>): void {
  if (!isRecord(state.population) || !isRecord(state.housing) || !isRecord(state.employment) || !isRecord(state.services) || !isRecord(state.environment) || !isRecord(state.budget)) throw contractError('estado da cidade incompleto');
  const population = state.population;
  requireNumberMap(population.residents_by_district, 'population.residents_by_district', true);
  for (const key of ['total_residents', 'urban_residents', 'rural_catchment_residents']) requireInteger(population[key], `population.${key}`, 0, Number.MAX_SAFE_INTEGER);
  const housing = state.housing;
  requireString(housing.initialization_method, 'housing.initialization_method');
  for (const key of ['occupied_households_reference_total', 'occupied_households_urban', 'total_units']) requireInteger(housing[key], `housing.${key}`, 0, Number.MAX_SAFE_INTEGER);
  if (typeof housing.vacancy_rate_target !== 'number' || !Number.isFinite(housing.vacancy_rate_target)) throw contractError('housing.vacancy_rate_target deve ser numérico');
  requireNumberMap(housing.units_by_district, 'housing.units_by_district', true);
  const employment = state.employment;
  requireNumberMap(employment.jobs_by_district, 'employment.jobs_by_district', true);
  requireInteger(employment.total_jobs, 'employment.total_jobs', 0, Number.MAX_SAFE_INTEGER);
  const services = state.services;
  for (const domain of ['school', 'primary_health']) {
    if (!isRecord(services[domain])) throw contractError(`services.${domain} ausente`);
    requireNumberMap(services[domain].demand_by_district, `services.${domain}.demand_by_district`);
    requireNumberMap(services[domain].capacity_by_district, `services.${domain}.capacity_by_district`);
  }
  requireNumberMap(state.environment.public_green_area_m2_by_district, 'environment.public_green_area_m2_by_district');
  const budget = state.budget;
  requireString(budget.currency, 'budget.currency');
  for (const key of ['credits_per_round', 'fixed_operations', 'reserve', 'discretionary_budget']) requireInteger(budget[key], `budget.${key}`, 0, Number.MAX_SAFE_INTEGER);
  for (const key of ['pending_effects', 'active_signal_plans']) {
    if (!Array.isArray(state[key]) || !state[key].every((event) => isRecord(event) && typeof event.event_id === 'string' && typeof event.event_type === 'string' &&
      Number.isInteger(event.effective_round) && isRecord(event.payload) && (event.source_action_id === null || typeof event.source_action_id === 'string'))) {
      throw contractError(`current_state.${key} contém eventos inválidos`);
    }
  }
}

function validateActionReceipt(value: unknown): void {
  if (!isRecord(value)) throw contractError('action receipt inválido');
  for (const key of ['action_id', 'action_type', 'code', 'message']) requireString(value[key], `action.${key}`);
  if (typeof value.accepted !== 'boolean' || !Array.isArray(value.charges) ||
      (value.effective_round !== null && !Number.isInteger(value.effective_round)) || (value.conflict_key !== null && typeof value.conflict_key !== 'string')) throw contractError('action receipt incompleto');
}

function parseIndicator(value: unknown): ArenaIndicatorDTO {
  if (!isRecord(value) || !isRecord(value.coverage)) throw contractError('indicador ou cobertura ausente');
  const indicator = value;
  const coverage = indicator.coverage as Record<string, unknown>;
  for (const key of ['indicator_id', 'indicator_version', 'unit', 'unit_basis', 'period', 'period_type', 'territory', 'formula_version', 'producer', 'producer_version']) {
    requireString(indicator[key], `indicator.${key}`);
  }
  if (indicator.value !== null && (typeof indicator.value !== 'number' || !Number.isFinite(indicator.value))) throw contractError('indicator.value deve ser número ou null');
  if (indicator.null_reason !== null && typeof indicator.null_reason !== 'string') throw contractError('indicator.null_reason deve ser string ou null');
  for (const key of ['source_kind', 'production_method', 'source_id', 'source_license', 'parent_state_hash', 'result_hash']) {
    if (indicator[key] !== null && typeof indicator[key] !== 'string') throw contractError(`indicator.${key} deve ser string ou null`);
  }
  if (indicator.seed !== null && !Number.isInteger(indicator.seed)) throw contractError('indicator.seed deve ser inteiro ou null');
  requireStringArray(indicator.limitations, 'indicator.limitations');
  for (const key of ['status', 'spatial', 'temporal']) requireString(coverage[key], `coverage.${key}`);
  for (const key of ['numerator', 'denominator']) requireNullableNumber(coverage[key], `coverage.${key}`);
  requireStringArray(coverage.filters, 'coverage.filters');
  return indicator as unknown as ArenaIndicatorDTO;
}

function parseArena(payload: unknown): ArenaJobDTO {
  if (!isRecord(payload) || !isRecord(payload.arena)) throw contractError('envelope { arena } ausente');
  const arena = payload.arena;
  if (typeof arena.arena_id !== 'string' || !STATUSES.includes(arena.status as ArenaStatus)) throw contractError('id ou status da arena inválido');
  if (arena.city_id !== CITY_ID || arena.provenance !== 'synthetic') throw contractError('a resposta não identifica a Aurora sintética');
  for (const key of ['experiment_id', 'snapshot_id', 'snapshot_hash', 'manifest_hash']) requireString(arena[key], `arena.${key}`);
  requireInteger(arena.horizon_rounds, 'horizon_rounds', 1, 10);
  requireInteger(arena.committed_rounds, 'committed_rounds', 0, arena.horizon_rounds as number);
  requireInteger(arena.completed_rounds, 'completed_rounds', 0, arena.committed_rounds as number);
  if (!isRecord(arena.manifest)) throw contractError('manifest ausente');
  for (const key of ['schema_version', 'profile_id', 'profile_version', 'parameter_version', 'snapshot_id', 'snapshot_hash', 'generator_version', 'transition_version', 'catalog_version', 'rules_version', 'provenance', 'manifest_hash']) requireString(arena.manifest[key], `manifest.${key}`);
  if (!isRecord(arena.manifest.parameters) || !isRecord(arena.manifest.seeds) || !Object.values(arena.manifest.seeds).every(Number.isInteger)) throw contractError('parâmetros ou seeds do manifest inválidos');
  if (arena.manifest.horizon_rounds !== arena.horizon_rounds || arena.manifest.provenance !== 'synthetic_config' ||
      arena.manifest.snapshot_id !== arena.snapshot_id || arena.manifest.snapshot_hash !== arena.snapshot_hash || arena.manifest.manifest_hash !== arena.manifest_hash || arena.manifest.experiment_id !== undefined && arena.manifest.experiment_id !== arena.experiment_id) {
    throw contractError('manifest não corresponde à arena sintética');
  }
  if (!Array.isArray(arena.instances) || arena.instances.length !== INSTANCE_COUNT) throw contractError('a arena deve conter exatamente cinco instâncias');
  const instanceIds = new Set<string>();
  for (const [index, raw] of arena.instances.entries()) {
    if (!isRecord(raw)) throw contractError(`instância ${index + 1} inválida`);
    const item = raw;
    for (const key of ['experiment_id', 'instance_id', 'agent_id', 'policy_id', 'policy_version', 'initial_city_state_hash', 'current_city_state_hash']) requireString(item[key], `instances[${index}].${key}`);
    if (item.experiment_id !== arena.experiment_id || instanceIds.has(item.instance_id as string)) throw contractError('instâncias duplicadas ou de outro experimento');
    instanceIds.add(item.instance_id as string);
    requireInteger(item.current_round_index, `instances[${index}].current_round_index`, 0, arena.horizon_rounds as number);
    if (item.current_state !== null) {
      if (!isRecord(item.current_state)) throw contractError('current_state deve ser objeto ou null');
      if (item.current_state.experiment_id !== arena.experiment_id || item.current_state.instance_id !== item.instance_id) throw contractError('current_state pertence a outra instância');
      for (const key of ['schema_version', 'transition_version', 'snapshot_hash', 'city_state_hash']) requireString(item.current_state[key], `current_state.${key}`);
      requireInteger(item.current_state.round_index, 'current_state.round_index', 0, arena.horizon_rounds as number);
      for (const key of ['parent_city_state_hash']) if (item.current_state[key] !== null && typeof item.current_state[key] !== 'string') throw contractError(`current_state.${key} deve ser string ou null`);
      validateCityState(item.current_state);
    }
    if (item.current_state === null && arena.status !== 'failed') throw contractError('current_state nulo só é permitido em arena failed');
  }
  if (!Array.isArray(arena.rounds) || arena.rounds.length !== arena.completed_rounds) throw contractError('rounds deve conter exatamente completed_rounds rodadas publicadas');
  const roundIndexes = new Set<number>();
  for (const [index, raw] of arena.rounds.entries()) {
    if (!isRecord(raw)) throw contractError(`rodada ${index + 1} inválida`);
    requireInteger(raw.round_index, `rounds[${index}].round_index`, 1, arena.horizon_rounds as number);
    if (raw.round_index !== index + 1 || roundIndexes.has(raw.round_index as number)) throw contractError('índice de rodada publicado fora de sequência ou duplicado');
    roundIndexes.add(raw.round_index as number);
    if (!Array.isArray(raw.instances) || raw.instances.length !== INSTANCE_COUNT) throw contractError(`rodada ${index + 1} deve conter exatamente cinco instâncias`);
    const roundInstanceIds = new Set<string>();
    for (const [instanceIndex, roundRaw] of raw.instances.entries()) {
      if (!isRecord(roundRaw)) throw contractError(`instância da rodada ${index + 1} inválida`);
      for (const key of ['instance_id', 'observed_city_state_hash', 'parent_city_state_hash', 'city_state_hash', 'manifest_hash', 'round_record_hash']) requireString(roundRaw[key], `rounds[${index}].instances[${instanceIndex}].${key}`);
      if (typeof roundRaw.instance_id !== 'string' || !instanceIds.has(roundRaw.instance_id) || roundInstanceIds.has(roundRaw.instance_id)) throw contractError('instâncias da rodada não correspondem às cinco instâncias da arena');
      roundInstanceIds.add(roundRaw.instance_id);
      if (!isRecord(roundRaw.proposal) || !isRecord(roundRaw.decision) || !Array.isArray(roundRaw.indicators)) throw contractError('detalhes da instância na rodada incompletos');
      for (const key of ['schema_version', 'experiment_id', 'proposal_id', 'idempotency_key', 'agent_id', 'instance_id', 'observed_city_state_hash', 'policy_id', 'policy_version', 'proposal_record_hash']) requireString(roundRaw.proposal[key], `proposal.${key}`);
      requireInteger(roundRaw.proposal.round_index, 'proposal.round_index', 1, arena.horizon_rounds as number);
      if (roundRaw.proposal.instance_id !== roundRaw.instance_id || roundRaw.proposal.experiment_id !== arena.experiment_id || roundRaw.proposal.round_index !== raw.round_index) throw contractError('proposta não corresponde à instância/rodada publicada');
      if (!Array.isArray(roundRaw.proposal.actions) || (roundRaw.proposal.budget_request !== null && !Number.isInteger(roundRaw.proposal.budget_request))) throw contractError('ações ou orçamento da proposta inválidos');
      for (const action of roundRaw.proposal.actions) {
        if (!isRecord(action)) throw contractError('ação proposta inválida');
        for (const key of ['action_id', 'action_type', 'target_id']) requireString(action[key], `proposal.action.${key}`);
        if (!isRecord(action.parameters) || (action.rationale !== null && typeof action.rationale !== 'string')) throw contractError('parâmetros da ação proposta inválidos');
      }
      for (const key of ['proposal_id', 'idempotency_key', 'proposal_hash', 'code']) requireString(roundRaw.decision[key], `decision.${key}`);
      if (typeof roundRaw.decision.accepted !== 'boolean' || !['accepted', 'rejected', 'no_action'].includes(String(roundRaw.decision.decision)) || !Array.isArray(roundRaw.decision.actions) || (roundRaw.decision.budget !== null && !isRecord(roundRaw.decision.budget))) throw contractError('decision inválida');
      for (const action of roundRaw.decision.actions) validateActionReceipt(action);
      for (const indicator of roundRaw.indicators) parseIndicator(indicator);
    }
  }
  if (arena.error !== null && (!isRecord(arena.error) || typeof arena.error.code !== 'string' || typeof arena.error.message !== 'string' ||
      (arena.error.round_index !== null && !Number.isInteger(arena.error.round_index)) || (arena.error.instance_id !== null && typeof arena.error.instance_id !== 'string'))) throw contractError('error deve conter code/message válidos e referências anuláveis');
  return arena as unknown as ArenaJobDTO;
}

async function requestJson(url: string, init: RequestInit, expectedStatus: number): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init.headers } });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new Error('Não foi possível conectar à API da Arena.');
  }
  if (!response.ok) throw new Error(`A API da Arena respondeu com erro HTTP ${response.status}.`);
  if (response.status !== expectedStatus) throw new Error(`A API da Arena respondeu com HTTP ${response.status}; esperado HTTP ${expectedStatus}.`);
  try { return await response.json() as unknown; } catch { throw new Error('A API da Arena retornou uma resposta que não é JSON válido.'); }
}

export async function startArena(horizonRounds: number): Promise<ArenaJobDTO> {
  if (!Number.isInteger(horizonRounds) || horizonRounds < 1 || horizonRounds > 10) throw new Error('O horizonte da Arena deve ser um inteiro entre 1 e 10.');
  const arena = parseArena(await requestJson(`${API_BASE_URL}/api/v1/arenas`, { method: 'POST', body: JSON.stringify({ horizon_rounds: horizonRounds }) }, 202));
  if (arena.status !== 'queued' || arena.horizon_rounds !== horizonRounds) throw contractError('POST não retornou a arena queued solicitada');
  return arena;
}

export async function fetchArena(arenaId: string): Promise<ArenaJobDTO> {
  if (typeof arenaId !== 'string' || arenaId.length === 0) throw new Error('O ID da Arena é obrigatório.');
  const arena = parseArena(await requestJson(`${API_BASE_URL}/api/v1/arenas/${encodeURIComponent(arenaId)}`, { method: 'GET' }, 200));
  if (arena.arena_id !== arenaId) throw contractError('a API retornou outra Arena durante o acompanhamento');
  return arena;
}
