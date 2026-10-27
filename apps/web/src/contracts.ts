export type Position = number[];

export interface LocalGeometry {
  type: string;
  coordinates?: unknown;
  geometries?: LocalGeometry[];
}

export interface LocalFeature {
  type: 'Feature';
  id?: string | number;
  geometry: LocalGeometry | null;
  properties: Record<string, unknown> | null;
}

export interface LocalFeatureCollection {
  type: 'LocalFeatureCollection';
  features: LocalFeature[];
}

export interface CityMetadata {
  city_id: string;
  snapshot_id: string;
  name: string;
  schema_version: string | number;
  provenance: string;
  hash: string;
  population: {
    total: number;
    urban?: number;
    rural_catchment?: number;
  };
  jobs: number;
}

export interface CityMap {
  city_id?: string;
  snapshot_id?: string;
  hash?: string;
  coordinate_space: string;
  bounds_m: [number, number, number, number];
  layers: {
    districts: LocalFeatureCollection;
    edges: LocalFeatureCollection;
    nodes: LocalFeatureCollection;
  };
}

export interface CityData {
  metadata: CityMetadata;
  map: CityMap;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireNumber(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Resposta inválida da API: ${path} deve ser um número.`);
  }
  return value;
}

export function parseMetadata(value: unknown): CityMetadata {
  if (!isRecord(value) || !isRecord(value.population)) {
    throw new Error('Resposta inválida da API: metadados da cidade ausentes.');
  }
  const population = value.population;
  if (typeof value.city_id !== 'string' || typeof value.snapshot_id !== 'string' ||
      typeof value.name !== 'string' || typeof value.hash !== 'string' ||
      typeof value.provenance !== 'string') {
    throw new Error('Resposta inválida da API: identidade ou proveniência da cidade ausente.');
  }
  return {
    city_id: value.city_id,
    snapshot_id: value.snapshot_id,
    name: value.name,
    schema_version: typeof value.schema_version === 'string' || typeof value.schema_version === 'number'
      ? value.schema_version : 'desconhecida',
    provenance: value.provenance,
    hash: value.hash,
    population: {
      total: requireNumber(population.total, 'population.total'),
      ...(typeof population.urban === 'number' ? { urban: population.urban } : {}),
      ...(typeof population.rural_catchment === 'number' ? { rural_catchment: population.rural_catchment } : {}),
    },
    jobs: requireNumber(value.jobs, 'jobs'),
  };
}

function parseFeatureCollection(value: unknown, name: string): LocalFeatureCollection {
  if (!isRecord(value) || value.type !== 'LocalFeatureCollection' || !Array.isArray(value.features)) {
    throw new Error(`Resposta inválida da API: camada ${name} não é LocalFeatureCollection.`);
  }
  const features = value.features.map((feature, index): LocalFeature => {
    if (!isRecord(feature) || feature.type !== 'Feature' ||
        (feature.geometry !== null && !isRecord(feature.geometry))) {
      throw new Error(`Resposta inválida da API: elemento ${index} da camada ${name}.`);
    }
    const geometry = feature.geometry as LocalGeometry | null;
    if (geometry && typeof geometry.type !== 'string') {
      throw new Error(`Resposta inválida da API: geometria ${index} da camada ${name} sem tipo.`);
    }
    return {
      type: 'Feature',
      ...(typeof feature.id === 'string' || typeof feature.id === 'number' ? { id: feature.id } : {}),
      geometry,
      properties: isRecord(feature.properties) ? feature.properties : null,
    };
  });
  return { type: 'LocalFeatureCollection', features };
}

export function parseCityMap(value: unknown): CityMap {
  if (!isRecord(value) || !isRecord(value.layers)) {
    throw new Error('Resposta inválida da API: mapa ou camadas ausentes.');
  }
  if (!Array.isArray(value.bounds_m) || value.bounds_m.length !== 4) {
    throw new Error('Resposta inválida da API: bounds_m deve conter quatro valores.');
  }
  const bounds = value.bounds_m.map((n, i) => requireNumber(n, `bounds_m[${i}]`));
  if (bounds[0] >= bounds[2] || bounds[1] >= bounds[3]) {
    throw new Error('Resposta inválida da API: limites do mapa sem área.');
  }
  if (typeof value.coordinate_space !== 'string') {
    throw new Error('Resposta inválida da API: coordinate_space ausente.');
  }
  if (value.coordinate_space !== 'synthetic_local_cartesian_m') {
    throw new Error('O mapa não está no espaço cartesiano local sintético esperado.');
  }
  const layers = value.layers;
  return {
    ...(typeof value.city_id === 'string' ? { city_id: value.city_id } : {}),
    ...(typeof value.snapshot_id === 'string' ? { snapshot_id: value.snapshot_id } : {}),
    ...(typeof value.hash === 'string' ? { hash: value.hash } : {}),
    coordinate_space: value.coordinate_space,
    bounds_m: bounds as [number, number, number, number],
    layers: {
      districts: parseFeatureCollection(layers.districts, 'districts'),
      edges: parseFeatureCollection(layers.edges, 'edges'),
      nodes: parseFeatureCollection(layers.nodes, 'nodes'),
    },
  };
}

export function assertSameSnapshot(metadata: CityMetadata, map: CityMap): void {
  const mismatch = (map.city_id && map.city_id !== metadata.city_id) ||
    (map.snapshot_id && map.snapshot_id !== metadata.snapshot_id) ||
    (map.hash && map.hash !== metadata.hash);
  if (mismatch) throw new Error('A API retornou metadados e mapa de snapshots diferentes. Tente novamente.');
}
