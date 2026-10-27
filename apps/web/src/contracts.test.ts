import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchAurora, startComparison, startSimulation } from './api';
import { assertSameSnapshot, parseCityMap, parseMetadata } from './contracts';
import { toDisplayCollection } from './local-display';

const metadataFixture = {
  city_id: 'aurora-base-v1', snapshot_id: 'aurora-base-v1:abc', name: 'Aurora', schema_version: '1',
  provenance: 'synthetic', hash: 'abc', population: { total: 67250, urban: 58783, rural_catchment: 8467 }, jobs: 24000,
};
const mapFixture = {
  city_id: 'aurora-base-v1', snapshot_id: 'aurora-base-v1:abc', hash: 'abc',
  coordinate_space: 'synthetic_local_cartesian_m', bounds_m: [0, 0, 6000, 6000],
  layers: {
    districts: { type: 'LocalFeatureCollection', features: [{ type: 'Feature', id: 'centro', geometry: { type: 'Polygon', coordinates: [[[0, 0], [1000, 0], [0, 0]]] }, properties: { name: 'Centro' } }] },
    edges: { type: 'LocalFeatureCollection', features: [] },
    nodes: { type: 'LocalFeatureCollection', features: [] },
  },
};

describe('HTTP response contracts', () => {
  it('accepts the documented metadata and local geometry contract', () => {
    expect(parseMetadata(metadataFixture).population.total).toBe(67250);
    const map = parseCityMap(mapFixture);
    expect(map.layers.districts.features).toHaveLength(1);
    expect(() => assertSameSnapshot(parseMetadata(metadataFixture), map)).not.toThrow();
  });

  it('rejects incomplete layer collections and mismatched snapshots', () => {
    expect(() => parseCityMap({ ...mapFixture, layers: { ...mapFixture.layers, nodes: null } })).toThrow(/LocalFeatureCollection/);
    expect(() => parseCityMap({ ...mapFixture, coordinate_space: 'EPSG:4326' })).toThrow(/cartesiano local sintético/);
    expect(() => assertSameSnapshot(parseMetadata(metadataFixture), parseCityMap({ ...mapFixture, hash: 'different' }))).toThrow(/snapshots diferentes/);
  });
});

describe('API integration', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('requests the metadata and map endpoints and returns their matching snapshot', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).endsWith('/map') ? mapFixture : metadataFixture;
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    const result = await fetchAurora(new AbortController().signal);
    expect(result.metadata.hash).toBe('abc');
    expect(fetchMock.mock.calls.map(([url]) => String(url)).sort()).toEqual([
      'http://127.0.0.1:8000/api/v1/cities/aurora-base-v1',
      'http://127.0.0.1:8000/api/v1/cities/aurora-base-v1/map',
    ]);
  });

  it('fails closed when either endpoint responds with an HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('unavailable', { status: 503 })));
    await expect(fetchAurora(new AbortController().signal)).rejects.toThrow(/HTTP 503/);
  });

  it('accepts reconciled simulation totals and requests the documented drain limit', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toMatchObject({ drain_limit_seconds: 3600 });
      return new Response(JSON.stringify({ simulation: {
        simulation_id: 'run-1', status: 'succeeded', city_id: 'aurora-base-v1', snapshot_id: 'snapshot-1',
        window_id: 'weekday_am_peak', seed: 42, drain_limit_seconds: 3600, engine_version: '1.20.0', warnings: [], error: null,
        metrics: { trips_requested: 930, trips_completed: 900, trips_not_completed: 30,
          mean_travel_time_seconds: 60, mean_speed_kmh: 30, mean_queue_length_meters: 10 },
      } }), { status: 202, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    const result = await startSimulation('weekday_am_peak');
    expect(result.metrics?.trips_not_completed).toBe(30);
  });

  it('requests a paired timing comparison and parses its per-metric deltas', async () => {
    const comparison = {
      comparison_id: 'comparison-1', status: 'succeeded',
      common_parameters: { city_id: 'aurora-base-v1', snapshot_id: 'aurora-base-v1:abc', snapshot_hash: 'abc',
        window_id: 'weekday_am_peak', seed: 42, drain_limit_seconds: 3600, trips_requested: 930, demand_hash: 'demand-hash' },
      intervention: { node_id: 'node:02:04', phases: [
        { movement: 'north_south', duration_seconds: 40 }, { movement: 'all_red', duration_seconds: 3 },
        { movement: 'east_west', duration_seconds: 20 }, { movement: 'all_red', duration_seconds: 3 },
      ] }, route_exposure: 'exposed',
      base_result: { simulation_id: 'base-1', engine: 'sumo', engine_version: '1.28.0' },
      intervention_result: { simulation_id: 'scenario-1', engine: 'sumo', engine_version: '1.28.0' },
      base_metrics: { trips_requested: 930, trips_completed: 920, trips_not_completed: 10, mean_travel_time_seconds: 60, mean_speed_kmh: 30, mean_queue_length_meters: 8 },
      intervention_metrics: { trips_requested: 930, trips_completed: 925, trips_not_completed: 5, mean_travel_time_seconds: 58, mean_speed_kmh: 31, mean_queue_length_meters: 7 },
      deltas: { trips_requested: 0, trips_completed: 5, trips_not_completed: -5, mean_travel_time_seconds: -2, mean_speed_kmh: 1, mean_queue_length_meters: -1 },
      base_warnings: [], intervention_warnings: [], error: null,
    };
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body).toMatchObject({ seed: 42, drain_limit_seconds: 3600, intervention: { node_id: 'node:02:04' } });
      expect(body.intervention.phases.map((phase: { duration_seconds: number }) => phase.duration_seconds)).toEqual([40, 3, 20, 3]);
      return new Response(JSON.stringify({ comparison }), { status: 202, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchMock);
    const result = await startComparison('weekday_am_peak');
    expect(result.base_metrics?.mean_queue_length_meters).toBe(8);
    expect(result.deltas?.mean_travel_time_seconds).toBe(-2);
    expect(result.intervention_result?.simulation_id).toBe('scenario-1');
    expect(result.route_exposure).toBe('exposed');
  });
});

describe('local display transform', () => {
  it('creates display geometry in memory while preserving the input local coordinates', () => {
    const input = parseCityMap(mapFixture).layers.districts;
    const rendered = toDisplayCollection(input, [0, 0, 6000, 6000]);
    expect(rendered.type).toBe('FeatureCollection');
    const displayedCoordinates = (rendered.features[0].geometry as { coordinates: number[][][] }).coordinates;
    expect(displayedCoordinates[0][0]).toEqual([-0.04, -0.04]);
    expect(displayedCoordinates[0][1][0]).toBeCloseTo(-0.0266666667);
    expect((input.features[0].geometry as { coordinates: number[][][] }).coordinates[0][0]).toEqual([0, 0]);
  });
});
