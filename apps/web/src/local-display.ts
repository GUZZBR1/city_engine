import type { CityMap, LocalFeature, LocalFeatureCollection } from './contracts';

export interface DisplayFeature {
  type: 'Feature';
  id?: string | number;
  geometry: { type: string; coordinates?: unknown; geometries?: unknown[] } | null;
  properties: Record<string, unknown> | null;
}

export interface DisplayCollection {
  type: 'FeatureCollection';
  features: DisplayFeature[];
}

/**
 * Produces an in-memory-only MapLibre representation. The affine coordinates
 * are a drawing device for the schematic canvas; they are never returned to
 * callers, persisted, or represented as real geographic data.
 */
export function toDisplayCollection(collection: LocalFeatureCollection, bounds: CityMap['bounds_m']): DisplayCollection {
  const [minX, minY, maxX, maxY] = bounds;
  const span = Math.max(maxX - minX, maxY - minY, 1);
  const scale = 0.08 / span;
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const transformCoordinates = (value: unknown): unknown => {
    if (Array.isArray(value) && value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number') {
      return [(value[0] - centerX) * scale, (value[1] - centerY) * scale, ...value.slice(2)];
    }
    if (Array.isArray(value)) return value.map(transformCoordinates);
    return value;
  };
  const transformGeometry = (geometry: LocalFeature['geometry']): DisplayFeature['geometry'] => {
    if (!geometry) return null;
    if ('coordinates' in geometry) return { type: geometry.type, coordinates: transformCoordinates(geometry.coordinates) };
    if ('geometries' in geometry) {
      return { type: geometry.type, geometries: geometry.geometries?.map((part) => transformGeometry(part) as unknown) };
    }
    return { type: geometry.type };
  };
  return {
    type: 'FeatureCollection',
    features: collection.features.map((feature) => ({
      type: 'Feature',
      ...(feature.id !== undefined ? { id: feature.id } : {}),
      geometry: transformGeometry(feature.geometry),
      properties: feature.properties,
    })),
  };
}
