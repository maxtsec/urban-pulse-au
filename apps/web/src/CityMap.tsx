import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { Feature, MultiPolygon, Polygon } from 'geojson';
import type { Development, Vehicle, Warning } from './city';
import tramIcon from './assets/tram.svg';
import buildingIcon from './assets/building.svg';
import { fixtureTracks } from './fixture-tracks';
import { placeLabels } from './labels';
import type { Box } from './labels';
import 'maplibre-gl/dist/maplibre-gl.css';

// Emit the worker and its imports as local build assets.
maplibregl.setWorkerUrl(workerUrl);

const TRAM_ICON = { halfWidth: 13, halfHeight: 16 };
const SITE_HALF = 15;
const FRESHNESS_ORDER = ['current', 'stale', 'unknown', 'expired'];

export type Insets = {
  top: number;
  right: number;
  bottom: number;
  left: number;
};

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
  showTracks: boolean;
  warnings: Warning[];
  showWarnings: boolean;
  developments: Development[];
  showPlanning: boolean;
  selectedDevelopment: string | null;
  onSelectDevelopment: (id: string) => void;
  /** Screen space covered by floating controls; the initial view fits inside the rest. */
  insets: Insets;
};

export function CityMap({
  boundary,
  vehicles,
  selected,
  onSelect,
  showVehicles,
  showBoundary,
  showTracks,
  warnings,
  showWarnings,
  developments,
  showPlanning,
  selectedDevelopment,
  onSelectDevelopment,
  insets,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<Map<string, maplibregl.Marker>>(new Map());
  const developmentMarkers = useRef<Map<string, maplibregl.Marker>>(new Map());
  const [ready, setReady] = useState<maplibregl.Map | null>(null);
  const [failed, setFailed] = useState(false);
  const initialInsets = useRef(insets);
  const labelOrder = useRef<string[]>([]);
  const frame = useRef(0);

  // Recompute label sides from current screen positions after any camera or marker change.
  const layoutLabels = useCallback(() => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const instance = map.current;
      if (!instance) return;
      const canvas = instance.getContainer();
      const point = (marker: maplibregl.Marker) =>
        instance.project(marker.getLngLat());
      const obstacles: Box[] = [];
      for (const marker of markers.current.values()) {
        const { x, y } = point(marker);
        obstacles.push({
          x: x - TRAM_ICON.halfWidth,
          y: y - TRAM_ICON.halfHeight,
          w: TRAM_ICON.halfWidth * 2,
          h: TRAM_ICON.halfHeight * 2,
        });
      }
      for (const marker of developmentMarkers.current.values()) {
        const { x, y } = point(marker);
        obstacles.push({
          x: x - SITE_HALF,
          y: y - SITE_HALF,
          w: SITE_HALF * 2,
          h: SITE_HALF * 2,
        });
      }
      const requests = labelOrder.current.flatMap((id) => {
        const marker = markers.current.get(id);
        const label = marker
          ?.getElement()
          .querySelector<HTMLElement>('.marker-label');
        if (!marker || !label) return [];
        const { x, y } = point(marker);
        return [
          { id, x, y, width: label.offsetWidth, height: label.offsetHeight },
        ];
      });
      const placement = placeLabels(requests, obstacles, TRAM_ICON, {
        width: canvas.clientWidth,
        height: canvas.clientHeight,
      });
      for (const [id, offset] of placement) {
        const element = markers.current.get(id)!.getElement();
        element.classList.toggle('label-collapsed', offset === null);
        if (offset) {
          element.style.setProperty('--label-x', `${offset.dx}px`);
          element.style.setProperty('--label-y', `${offset.dy}px`);
        } else {
          // A collapsed label reappears on hover/focus at the default right side.
          element.style.removeProperty('--label-x');
          element.style.removeProperty('--label-y');
        }
      }
    });
  }, []);

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
              paint: { 'background-color': '#eef1ef' },
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
        'bottom-right',
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
          paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.85 },
        });
        instance.addLayer({
          id: 'area-line',
          type: 'line',
          source: 'southbank',
          paint: {
            'line-color': '#7d8a85',
            'line-width': 1.5,
            'line-dasharray': [3, 2],
          },
        });
        instance.addSource('warnings', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] },
        });
        instance.addLayer({
          id: 'warning-fill',
          type: 'fill',
          source: 'warnings',
          paint: { 'fill-color': '#d9822b', 'fill-opacity': 0.14 },
        });
        instance.addLayer({
          id: 'warning-line',
          type: 'line',
          source: 'warnings',
          paint: {
            'line-color': '#b8661c',
            'line-width': 2,
            'line-dasharray': [2, 2],
          },
        });
        instance.addSource('fixture-tracks', {
          type: 'geojson',
          data: fixtureTracks,
        });
        instance.addLayer({
          id: 'track-ties',
          type: 'line',
          source: 'fixture-tracks',
          paint: {
            'line-color': '#c3cbc8',
            'line-width': 9,
            'line-dasharray': [0.15, 1.3],
          },
        });
        instance.addLayer({
          id: 'track-rails',
          type: 'line',
          source: 'fixture-tracks',
          layout: { 'line-join': 'round' },
          paint: { 'line-color': '#a3aeaa', 'line-width': 4.5 },
        });
        instance.addLayer({
          id: 'track-center',
          type: 'line',
          source: 'fixture-tracks',
          layout: { 'line-join': 'round' },
          paint: { 'line-color': '#ffffff', 'line-width': 2 },
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
        instance.fitBounds(bounds, {
          padding: initialInsets.current,
          duration: 0,
        });
        setReady(instance);
        setFailed(false);
      });
      instance.on('move', layoutLabels);
      instance.on('error', () => setFailed(true));
    } catch {
      setFailed(true);
      return;
    }
    const resize = new ResizeObserver(() => {
      instance.resize();
      layoutLabels();
    });
    resize.observe(container.current);
    return () => {
      cancelAnimationFrame(frame.current);
      resize.disconnect();
      markers.current.forEach((marker) => marker.remove());
      markers.current.clear();
      developmentMarkers.current.forEach((marker) => marker.remove());
      developmentMarkers.current.clear();
      map.current = null;
      instance.remove();
    };
  }, [boundary, layoutLabels]);

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
    for (const layer of ['track-ties', 'track-rails', 'track-center']) {
      instance.setLayoutProperty(
        layer,
        'visibility',
        showTracks ? 'visible' : 'none',
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
        const icon = document.createElement('img');
        icon.src = tramIcon;
        icon.alt = '';
        icon.draggable = false;
        icon.setAttribute('aria-hidden', 'true');
        const label = document.createElement('span');
        label.className = 'marker-label';
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
    // The selected tram claims its preferred label side first, then fresher observations.
    labelOrder.current = [...visible]
      .sort(
        (a, b) =>
          Number(b.id === selected) - Number(a.id === selected) ||
          FRESHNESS_ORDER.indexOf(a.freshness) -
            FRESHNESS_ORDER.indexOf(b.freshness) ||
          a.label.localeCompare(b.label),
      )
      .map((vehicle) => vehicle.id);
    layoutLabels();
  }, [
    ready,
    vehicles,
    selected,
    onSelect,
    showVehicles,
    showBoundary,
    showTracks,
    layoutLabels,
  ]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || ready !== instance) return;
    const visible = showPlanning
      ? developments.filter(
          (record) => record.position && record.applicable === true,
        )
      : [];
    const ids = new Set(visible.map((record) => record.development_key));
    for (const [id, marker] of developmentMarkers.current) {
      if (!ids.has(id)) {
        marker.remove();
        developmentMarkers.current.delete(id);
      }
    }
    for (const record of visible) {
      let marker = developmentMarkers.current.get(record.development_key);
      if (!marker) {
        const button = document.createElement('button');
        button.type = 'button';
        const icon = document.createElement('img');
        icon.src = buildingIcon;
        icon.alt = '';
        icon.draggable = false;
        button.append(icon);
        button.addEventListener('click', () =>
          onSelectDevelopment(record.development_key),
        );
        marker = new maplibregl.Marker({ element: button })
          .setLngLat([record.position!.longitude, record.position!.latitude])
          .addTo(instance);
        developmentMarkers.current.set(record.development_key, marker);
      }
      const button = marker.getElement();
      button.setAttribute('aria-label', `Inspect ${record.name} on map`);
      button.setAttribute(
        'aria-pressed',
        String(record.development_key === selectedDevelopment),
      );
      button.title = `${record.name} · ${record.status}`;
      button.className = `development-marker ${record.development_key === selectedDevelopment ? 'selected' : ''} maplibregl-marker maplibregl-marker-anchor-center`;
      marker.setLngLat([record.position!.longitude, record.position!.latitude]);
    }
    layoutLabels();
  }, [
    ready,
    developments,
    showPlanning,
    selectedDevelopment,
    onSelectDevelopment,
    layoutLabels,
  ]);

  const visibleWarnings = useMemo(
    () =>
      showWarnings
        ? warnings.filter(
            (warning) => warning.lifecycle === 'active' && warning.geometry,
          )
        : [],
    [showWarnings, warnings],
  );
  useEffect(() => {
    const instance = map.current;
    if (!instance || ready !== instance) return;
    const source = instance.getSource('warnings') as maplibregl.GeoJSONSource;
    source.setData({
      type: 'FeatureCollection',
      features: visibleWarnings.map((warning) => ({
        type: 'Feature',
        geometry: warning.geometry!,
        properties: { id: warning.id },
      })),
    });
  }, [ready, visibleWarnings]);

  return (
    <div className="map-shell">
      <div
        className="map-canvas"
        ref={container}
        aria-label="Southbank city map"
        data-testid="map"
      />
      {failed && (
        <p className="map-fallback" role="status">
          Map unavailable. The details panel retains tram observations and
          development information.
        </p>
      )}
      <div className="map-credit">
        Boundary:{' '}
        <a href={boundary.feature.properties.source_url}>City of Melbourne</a> ·{' '}
        <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> ·
        Illustrative tracks · No basemap
      </div>
    </div>
  );
}
