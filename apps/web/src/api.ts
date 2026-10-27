import { assertSameSnapshot, parseCityMap, parseMetadata, type CityData } from './contracts';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const CITY_ID = 'aurora-base-v1';

async function getJson(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) {
    throw new Error(`A API respondeu com erro HTTP ${response.status}.`);
  }
  try {
    return await response.json() as unknown;
  } catch {
    throw new Error('A API retornou uma resposta que não é JSON válido.');
  }
}

export async function fetchAurora(signal: AbortSignal): Promise<CityData> {
  const [metadataJson, mapJson] = await Promise.all([
    getJson(`${API_BASE_URL}/api/v1/cities/${CITY_ID}`, signal),
    getJson(`${API_BASE_URL}/api/v1/cities/${CITY_ID}/map`, signal),
  ]);
  const metadata = parseMetadata(metadataJson);
  const map = parseCityMap(mapJson);
  if (metadata.city_id !== CITY_ID) throw new Error('A API retornou uma cidade diferente de Aurora.');
  if (metadata.provenance.toLowerCase() !== 'synthetic') {
    throw new Error('A proveniência retornada pela API não identifica dados sintéticos.');
  }
  assertSameSnapshot(metadata, map);
  return { metadata, map };
}

export interface SimulationMetrics {
  trips_requested: number;
  trips_completed: number;
  trips_not_completed: number;
  mean_travel_time_seconds: number | null;
  mean_speed_kmh: number | null;
  mean_queue_length_meters: number | null;
}

export type SimulationStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export interface Simulation {
  simulation_id: string;
  status: SimulationStatus;
  city_id: string;
  snapshot_id: string;
  window_id: string;
  seed: number;
  drain_limit_seconds: number;
  engine_version: string;
  metrics: SimulationMetrics | null;
  warnings: string[];
  error?: { code?: string; message?: string } | null;
}

export interface ComparisonDeltas {
  trips_requested: number;
  trips_completed: number;
  trips_not_completed: number;
  mean_travel_time_seconds: number | null;
  mean_speed_kmh: number | null;
  mean_queue_length_meters: number | null;
}

export type ComparisonStatus = 'queued' | 'running' | 'succeeded' | 'failed';
export interface SimulationComparison {
  comparison_id: string;
  status: ComparisonStatus;
  common_parameters: {
    city_id: string;
    snapshot_id: string;
    snapshot_hash: string;
    window_id: string;
    seed: number;
    drain_limit_seconds: number;
    trips_requested: number;
    demand_hash: string;
  };
  intervention: { node_id: string; phases: { movement: string; duration_seconds: number }[] };
  base_result: { simulation_id: string; engine: string; engine_version: string } | null;
  intervention_result: { simulation_id: string; engine: string; engine_version: string } | null;
  base_metrics: SimulationMetrics | null;
  intervention_metrics: SimulationMetrics | null;
  deltas: ComparisonDeltas | null;
  base_warnings: string[];
  intervention_warnings: string[];
  error: { code: string; scenario: 'base' | 'intervention' | null; message: string } | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseSimulation(value: unknown): Simulation {
  if (!isRecord(value) || !isRecord(value.simulation)) throw new Error('Resposta inválida da API: simulação ausente.');
  const sim = value.simulation;
  const statuses: SimulationStatus[] = ['queued', 'running', 'succeeded', 'failed', 'cancelled'];
  if (typeof sim.simulation_id !== 'string' || !statuses.includes(sim.status as SimulationStatus) ||
      typeof sim.city_id !== 'string' || typeof sim.snapshot_id !== 'string' || typeof sim.window_id !== 'string' ||
      typeof sim.seed !== 'number' || typeof sim.drain_limit_seconds !== 'number' || typeof sim.engine_version !== 'string' || !Array.isArray(sim.warnings)) {
    throw new Error('Resposta inválida da API: metadados ou estado da simulação incompletos.');
  }
  let metrics: SimulationMetrics | null = null;
  if (sim.metrics !== null) {
    if (!isRecord(sim.metrics)) throw new Error('Resposta inválida da API: métricas ausentes ou incompletas.');
    const rawMetrics = sim.metrics;
    const requiredKeys = ['trips_requested', 'trips_completed', 'trips_not_completed'] as const;
    const nullableKeys = ['mean_travel_time_seconds', 'mean_speed_kmh', 'mean_queue_length_meters'] as const;
    if (!requiredKeys.every((key) => typeof rawMetrics[key] === 'number' && Number.isFinite(rawMetrics[key])) ||
        !nullableKeys.every((key) => rawMetrics[key] === null || (typeof rawMetrics[key] === 'number' && Number.isFinite(rawMetrics[key])))) {
      throw new Error('Resposta inválida da API: métricas incompletas.');
    }
    if ((rawMetrics.trips_completed as number) + (rawMetrics.trips_not_completed as number) !== rawMetrics.trips_requested) {
      throw new Error('Resposta inválida da API: totais de viagens inconsistentes.');
    }
    metrics = Object.fromEntries([...requiredKeys, ...nullableKeys].map((key) => [key, rawMetrics[key]])) as unknown as SimulationMetrics;
  }
  if (sim.status === 'succeeded' && metrics === null) throw new Error('A API concluiu a simulação sem retornar métricas.');
  if (sim.status !== 'succeeded' && metrics !== null) throw new Error('Resposta inválida da API: métricas inesperadas antes da conclusão.');
  return { ...sim, status: sim.status as SimulationStatus, metrics, warnings: sim.warnings.filter((item): item is string => typeof item === 'string') } as Simulation;
}

async function requestJson(url: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(url, { ...init, headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init.headers } });
  if (!response.ok) throw new Error(`A API respondeu com erro HTTP ${response.status}.`);
  try { return await response.json() as unknown; } catch { throw new Error('A API retornou uma resposta que não é JSON válido.'); }
}

function parseComparisonMetrics(value: unknown): SimulationMetrics | null {
  if (value === null) return null;
  if (!isRecord(value)) throw new Error('Resposta inválida da API: métricas de comparação ausentes.');
  const countKeys = ['trips_requested', 'trips_completed', 'trips_not_completed'] as const;
  const averageKeys = ['mean_travel_time_seconds', 'mean_speed_kmh', 'mean_queue_length_meters'] as const;
  if (!countKeys.every((key) => Number.isInteger(value[key]) && (value[key] as number) >= 0) ||
      !averageKeys.every((key) => value[key] === null || (typeof value[key] === 'number' && Number.isFinite(value[key])))) {
    throw new Error('Resposta inválida da API: métricas de comparação incompletas.');
  }
  if ((value.trips_completed as number) + (value.trips_not_completed as number) !== value.trips_requested) {
    throw new Error('Resposta inválida da API: totais de viagens inconsistentes.');
  }
  return Object.fromEntries([...countKeys, ...averageKeys].map((key) => [key, value[key]])) as unknown as SimulationMetrics;
}

function parseComparison(value: unknown): SimulationComparison {
  if (!isRecord(value) || !isRecord(value.comparison)) throw new Error('Resposta inválida da API: comparação ausente.');
  const comparison = value.comparison;
  const statuses: ComparisonStatus[] = ['queued', 'running', 'succeeded', 'failed'];
  if (typeof comparison.comparison_id !== 'string' || !statuses.includes(comparison.status as ComparisonStatus) ||
      !isRecord(comparison.common_parameters) || !isRecord(comparison.intervention) ||
      !Array.isArray(comparison.base_warnings) || !Array.isArray(comparison.intervention_warnings)) {
    throw new Error('Resposta inválida da API: comparação incompleta.');
  }
  const common = comparison.common_parameters;
  if (typeof common.city_id !== 'string' || typeof common.snapshot_id !== 'string' || typeof common.snapshot_hash !== 'string' ||
      typeof common.window_id !== 'string' || !Number.isInteger(common.seed) || !Number.isInteger(common.drain_limit_seconds) ||
      !Number.isInteger(common.trips_requested) || typeof common.demand_hash !== 'string') {
    throw new Error('Resposta inválida da API: parâmetros comuns incompletos.');
  }
  const baseMetrics = parseComparisonMetrics(comparison.base_metrics);
  const interventionMetrics = parseComparisonMetrics(comparison.intervention_metrics);
  let deltas: ComparisonDeltas | null = null;
  if (comparison.deltas !== null) {
    if (!isRecord(comparison.deltas)) throw new Error('Resposta inválida da API: deltas ausentes.');
    const rawDeltas = comparison.deltas;
    const counts = ['trips_requested', 'trips_completed', 'trips_not_completed'] as const;
    const averages = ['mean_travel_time_seconds', 'mean_speed_kmh', 'mean_queue_length_meters'] as const;
    if (!counts.every((key) => Number.isInteger(rawDeltas[key])) ||
        !averages.every((key) => rawDeltas[key] === null || (typeof rawDeltas[key] === 'number' && Number.isFinite(rawDeltas[key])))) {
      throw new Error('Resposta inválida da API: deltas incompletos.');
    }
    deltas = Object.fromEntries([...counts, ...averages].map((key) => [key, rawDeltas[key]])) as unknown as ComparisonDeltas;
  }
  if (comparison.status === 'succeeded' && (!baseMetrics || !interventionMetrics || !deltas || !isRecord(comparison.base_result) || !isRecord(comparison.intervention_result))) {
    throw new Error('A API concluiu a comparação sem os dois resultados e seus deltas.');
  }
  if (comparison.status !== 'succeeded' && (baseMetrics || interventionMetrics || deltas)) {
    throw new Error('Resposta inválida da API: resultados parciais não podem ser publicados.');
  }
  return { ...comparison, status: comparison.status as ComparisonStatus, base_metrics: baseMetrics,
    intervention_metrics: interventionMetrics, deltas, base_warnings: comparison.base_warnings.filter((item): item is string => typeof item === 'string'),
    intervention_warnings: comparison.intervention_warnings.filter((item): item is string => typeof item === 'string') } as SimulationComparison;
}

export async function startSimulation(windowId: string): Promise<Simulation> {
  const simulation = parseSimulation(await requestJson(`${API_BASE_URL}/api/v1/simulations`, {
    method: 'POST', body: JSON.stringify({ city_id: CITY_ID, window_id: windowId, seed: 42, drain_limit_seconds: 3600 }),
  }));
  if (simulation.city_id !== CITY_ID || simulation.window_id !== windowId || simulation.seed !== 42) {
    throw new Error('A API retornou uma execução diferente da solicitada.');
  }
  return simulation;
}

export async function fetchSimulation(id: string, signal: AbortSignal): Promise<Simulation> {
  const simulation = parseSimulation(await requestJson(`${API_BASE_URL}/api/v1/simulations/${encodeURIComponent(id)}`, { method: 'GET', signal }));
  if (simulation.simulation_id !== id) throw new Error('A API retornou outra execução durante o acompanhamento.');
  return simulation;
}

export async function startComparison(windowId: string): Promise<SimulationComparison> {
  return parseComparison(await requestJson(`${API_BASE_URL}/api/v1/comparisons`, {
    method: 'POST', body: JSON.stringify({
      city_id: CITY_ID,
      window_id: windowId,
      seed: 42,
      drain_limit_seconds: 3600,
      intervention: {
        node_id: 'node:02:00',
        phases: [
          { movement: 'north_south', duration_seconds: 40 },
          { movement: 'all_red', duration_seconds: 3 },
          { movement: 'east_west', duration_seconds: 20 },
          { movement: 'all_red', duration_seconds: 3 },
        ],
      },
    }),
  }));
}

export async function fetchComparison(id: string, signal: AbortSignal): Promise<SimulationComparison> {
  const comparison = parseComparison(await requestJson(`${API_BASE_URL}/api/v1/comparisons/${encodeURIComponent(id)}`, { method: 'GET', signal }));
  if (comparison.comparison_id !== id) throw new Error('A API retornou outra comparação durante o acompanhamento.');
  return comparison;
}

export const apiBaseUrl = API_BASE_URL;
