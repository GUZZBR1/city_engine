import { useCallback, useEffect, useRef } from 'react';
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl';
import type { CityMap } from './contracts';
import { toDisplayCollection } from './local-display';

interface Props {
  cityMap: CityMap;
  visible: { districts: boolean; edges: boolean; nodes: boolean };
}

const sourceFor = (id: string) => `${id}-source`;
const layerFor = (id: string) => `${id}-layer`;

export function MapView({ cityMap, visible }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const dataRef = useRef(cityMap);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;

  const fitCity = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const [minX, minY, maxX, maxY] = dataRef.current.bounds_m;
    const span = Math.max(maxX - minX, maxY - minY, 1);
    const scale = 0.08 / span;
    const toLngLat = (x: number, y: number): [number, number] => [
      (x - (minX + maxX) / 2) * scale,
      (y - (minY + maxY) / 2) * scale,
    ];
    const southwest = toLngLat(minX, minY);
    const northeast = toLngLat(maxX, maxY);
    map.fitBounds([southwest, northeast], { padding: 46, duration: 300, maxZoom: 15 });
  }, []);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      // No raster/vector basemap or external tile source. Coordinates are an
      // ephemeral affine drawing transform of the API's local metric grid.
      style: {
        version: 8,
        sources: {},
        layers: [{ id: 'canvas', type: 'background', paint: { 'background-color': '#f4f3ee' } }],
      },
      center: [0, 0],
      zoom: 12,
      attributionControl: false,
      maxZoom: 18,
      minZoom: 8,
      cooperativeGestures: true,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    mapRef.current = map;
    map.once('load', () => {
      const current = dataRef.current;
      const layers = [
        ['districts', current.layers.districts, 'fill'] as const,
        ['edges', current.layers.edges, 'line'] as const,
        ['nodes', current.layers.nodes, 'circle'] as const,
      ];
      for (const [id, collection, kind] of layers) {
        map.addSource(sourceFor(id), {
          type: 'geojson',
          data: toDisplayCollection(collection, current.bounds_m) as never,
        });
        if (kind === 'fill') {
          map.addLayer({
            id: layerFor(id), type: 'fill', source: sourceFor(id),
            paint: { 'fill-color': '#73a88e', 'fill-opacity': 0.34, 'fill-outline-color': '#326b55' },
          });
          map.addLayer({
            id: `${layerFor(id)}-name`, type: 'symbol', source: sourceFor(id),
            layout: { 'text-field': ['coalesce', ['get', 'name'], ['get', 'label'], ['get', 'id'], ''], 'text-size': 12, 'text-font': ['Open Sans Regular'] },
            paint: { 'text-color': '#234538', 'text-halo-color': '#f4f3ee', 'text-halo-width': 1.2 },
          });
        } else if (kind === 'line') {
          map.addLayer({
            id: layerFor(id), type: 'line', source: sourceFor(id),
            paint: { 'line-color': '#b45f36', 'line-width': 2.2, 'line-opacity': 0.95 },
          });
        } else {
          map.addLayer({
            id: layerFor(id), type: 'circle', source: sourceFor(id),
            paint: { 'circle-radius': 4.2, 'circle-color': '#345f94', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#f4f3ee' },
          });
        }
        const visibility = visibleRef.current[id as keyof Props['visible']] ? 'visible' : 'none';
        map.setLayoutProperty(layerFor(id), 'visibility', visibility);
        if (map.getLayer(`${layerFor(id)}-name`)) map.setLayoutProperty(`${layerFor(id)}-name`, 'visibility', visibility);
      }
      fitCity();
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [fitCity]);

  useEffect(() => {
    dataRef.current = cityMap;
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    for (const [id, collection] of Object.entries(cityMap.layers)) {
      const source = map.getSource(sourceFor(id)) as maplibregl.GeoJSONSource | undefined;
      source?.setData(toDisplayCollection(collection, cityMap.bounds_m) as never);
    }
    fitCity();
  }, [cityMap, fitCity]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    for (const [id, isVisible] of Object.entries(visible)) {
      const visibility = isVisible ? 'visible' : 'none';
      if (map.getLayer(layerFor(id))) map.setLayoutProperty(layerFor(id), 'visibility', visibility);
      if (map.getLayer(`${layerFor(id)}-name`)) map.setLayoutProperty(`${layerFor(id)}-name`, 'visibility', visibility);
    }
  }, [visible]);

  return (
    <section className="map-frame" aria-labelledby="map-title">
      <div className="map-heading">
        <div>
          <p className="eyebrow">VISUALIZAÇÃO 2D</p>
          <h2 id="map-title">Esquema territorial</h2>
        </div>
        <button className="quiet-button" onClick={fitCity} type="button" aria-label="Enquadrar toda a cidade no mapa">
          Enquadrar cidade
        </button>
      </div>
      <div ref={containerRef} className="map-canvas" role="img" aria-label="Mapa esquemático de Aurora com distritos, vias e cruzamentos; use a tabela abaixo como alternativa acessível" />
      <p className="map-note">Esquema sintético local · coordenadas métricas convertidas só para exibição · sem localização geográfica real</p>
    </section>
  );
}
