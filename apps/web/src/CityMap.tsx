import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { Feature, MultiPolygon, Polygon } from 'geojson';
import type { Vehicle } from './city';
import 'maplibre-gl/dist/maplibre-gl.css';

// Emit the worker and its imports as local build assets.
maplibregl.setWorkerUrl(workerUrl);

export type Boundary = {
  revision: string;
  feature: Feature<
    Polygon | MultiPolygon,
    { provider: string; licence: string; source_url: string }
  >;
};

type Props = {
  boundary: Boundary;
  vehicles: Vehicle[];
  selected: string | null;
  onSelect: (id: string) => void;
  showVehicles: boolean;
  showBoundary: boolean;
};

export function CityMap({
  boundary,
  vehicles,
  selected,
  onSelect,
  showVehicles,
  showBoundary,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<Map<string, maplibregl.Marker>>(new Map());
  const [ready, setReady] = useState<maplibregl.Map | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!container.current) return;
    let instance: maplibregl.Map;
    try {
      instance = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          sources: {},
          layers: [
            {
              id: 'background',
              type: 'background',
              paint: { 'background-color': '#eaf0eb' },
            },
          ],
        },
        center: [144.962, -37.825],
        zoom: 14,
        attributionControl: false,
        refreshExpiredTiles: false,
      });
      map.current = instance;
      instance.addControl(
        new maplibregl.NavigationControl({ showCompass: false }),
        'top-right',
      );
      instance.on('load', () => {
        instance.addSource('southbank', {
          type: 'geojson',
          data: boundary.feature,
        });
        instance.addLayer({
          id: 'area-fill',
          type: 'fill',
          source: 'southbank',
          paint: { 'fill-color': '#c4d9cd', 'fill-opacity': 0.72 },
        });
        instance.addLayer({
          id: 'area-line',
          type: 'line',
          source: 'southbank',
          paint: {
            'line-color': '#7d9b89',
            'line-width': 2,
            'line-dasharray': [3, 2],
          },
        });
        const bounds = new maplibregl.LngLatBounds();
        const polygons =
          boundary.feature.geometry.type === 'Polygon'
            ? [boundary.feature.geometry.coordinates]
            : boundary.feature.geometry.coordinates;
        polygons.forEach((polygon) =>
          polygon.forEach((ring) =>
            ring.forEach((point) => bounds.extend([point[0], point[1]])),
          ),
        );
        instance.fitBounds(bounds, { padding: 50, duration: 0 });
        setReady(instance);
        setFailed(false);
      });
      instance.on('error', () => setFailed(true));
    } catch {
      setFailed(true);
      return;
    }
    const resize = new ResizeObserver(() => instance.resize());
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      markers.current.forEach((marker) => marker.remove());
      markers.current.clear();
      map.current = null;
      instance.remove();
    };
  }, [boundary]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || ready !== instance) return;
    for (const layer of ['area-fill', 'area-line']) {
      instance.setLayoutProperty(
        layer,
        'visibility',
        showBoundary ? 'visible' : 'none',
      );
    }
    const visible = showVehicles
      ? vehicles.filter((vehicle) => vehicle.visible_on_map)
      : [];
    const ids = new Set(visible.map((vehicle) => vehicle.id));
    for (const [id, marker] of markers.current) {
      if (!ids.has(id)) {
        marker.remove();
        markers.current.delete(id);
      }
    }
    visible.forEach((vehicle) => {
      let marker = markers.current.get(vehicle.id);
      if (!marker) {
        const button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('aria-label', `Select ${vehicle.label} on map`);
        button.dataset.testid = `marker-${vehicle.label.replace(' ', '-')}`;
        const icon = document.createElement('span');
        icon.textContent = '▥';
        icon.setAttribute('aria-hidden', 'true');
        const label = document.createElement('span');
        label.textContent = vehicle.label;
        button.append(icon, label);
        button.addEventListener('click', () => onSelect(vehicle.id));
        marker = new maplibregl.Marker({ element: button })
          .setLngLat([vehicle.longitude, vehicle.latitude])
          .addTo(instance);
        markers.current.set(vehicle.id, marker);
      }
      const button = marker.getElement();
      button.className = `tram-marker ${vehicle.freshness} ${vehicle.id === selected ? 'selected' : ''} maplibregl-marker maplibregl-marker-anchor-center`;
      button.setAttribute('aria-pressed', String(vehicle.id === selected));
      marker.setLngLat([vehicle.longitude, vehicle.latitude]);
    });
  }, [ready, vehicles, selected, onSelect, showVehicles, showBoundary]);

  return (
    <div className="map-shell">
      <div
        className="map-canvas"
        ref={container}
        aria-label="Southbank tram map"
        data-testid="map"
      />
      <div className="map-caption">
        <span className="dot" /> Southbank CLUE area
      </div>
      {failed && (
        <p className="map-fallback" role="status">
          Map unavailable. The tram list below has the same observations.
        </p>
      )}
      <div className="map-legend">
        <span>
          <i className="legend-dot" /> Current
        </span>
        <span>
          <i className="legend-dot stale" /> Stale
        </span>
        <span>
          <i className="legend-dot unknown" /> Time unknown
        </span>
      </div>
      <div className="map-credit">
        Boundary:{' '}
        <a href={boundary.feature.properties.source_url}>City of Melbourne</a> ·{' '}
        <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> ·
        No basemap
      </div>
    </div>
  );
}
