import { MapLibreOverlay } from '@deck.gl/maplibre';
import { ScenegraphLayer } from '@deck.gl/mesh-layers';
import { LineLayer, PolygonLayer, ScatterplotLayer } from '@deck.gl/layers';
import type { Map } from 'maplibre-gl';
import type { Layer } from '@deck.gl/core';
import { loadBuildings } from '../buildings';
import type { Mass } from '../buildings';
import type { Development } from '../city';
import type { DemoTram, WeatherKind } from './day';
import tramUrl from '../assets/demo-tram.glb?url';
import craneUrl from '../assets/demo-crane.glb?url';
import plannedUrl from '../assets/demo-planned.glb?url';

export type VisualScene = {
  buildingsUrl?: string;
  buildingHash?: string;
  trams: DemoTram[];
  sites: Development[];
  clock: number;
  weather: WeatherKind;
  weatherVisible: boolean;
  buildingsVisible: boolean;
  selected: string | null;
  select: (id: string) => void;
};
function modelLayers(scene: VisualScene, drawn: (id: string) => void): Layer[] {
  const common = {
    pickable: true,
    _lighting: 'pbr' as const,
    parameters: { depthCompare: 'always' as const, depthWriteEnabled: false },
    // Model coordinates are metres: zoom changes projected size naturally.
    sizeScale: 3,
  };
  const siteLayer = (construction: boolean) =>
    new ScenegraphLayer<Development>({
      ...common,
      sizeScale: 1.5,
      id: construction ? 'demo-cranes' : 'demo-planned',
      onFirstDraw: () => drawn(construction ? 'demo-cranes' : 'demo-planned'),
      scenegraph: construction ? craneUrl : plannedUrl,
      data: scene.sites.filter(
        (site) =>
          (site.status.toUpperCase() === 'UNDER CONSTRUCTION') ===
            construction &&
          site.position &&
          site.applicable,
      ),
      getPosition: (site) => [
        site.position!.longitude,
        site.position!.latitude,
        2,
      ],
      getOrientation: [0, 0, 90],
      getColor: [255, 255, 255, 255],
      onClick: ({ object }) => {
        if (object) scene.select(object.development_key);
      },
    });
  return [
    new ScenegraphLayer<DemoTram>({
      ...common,
      id: 'demo-trams',
      onFirstDraw: () => drawn('demo-trams'),
      scenegraph: tramUrl,
      data: scene.trams,
      getPosition: (tram) => [tram.longitude, tram.latitude, 3],
      getOrientation: (tram) => [0, 180 - tram.heading, 90],
      getColor: (tram) =>
        tram.demoDelay === 'severe'
          ? [255, 65, 75, 255]
          : tram.demoDelay === 'affected'
            ? [255, 190, 40, 255]
            : [255, 255, 255, 255],
      onClick: ({ object }) => {
        if (object) scene.select(object.id);
      },
    }),
    new ScatterplotLayer<DemoTram>({
      id: 'demo-delay-halos',
      data: scene.trams.filter((t) => t.demoDelay),
      getPosition: (t) => [t.longitude, t.latitude, 4],
      getRadius: 20,
      radiusMinPixels: 10,
      filled: false,
      stroked: true,
      lineWidthMinPixels: 3,
      parameters: { depthCompare: 'always', depthWriteEnabled: false },
      getLineColor: (t) =>
        t.demoDelay === 'severe' ? [220, 55, 70, 255] : [222, 154, 20, 255],
    }),
    siteLayer(true),
    siteLayer(false),
    new ScatterplotLayer({
      id: 'demo-selection',
      data: [
        ...scene.trams.map((t) => ({
          id: t.id,
          position: [t.longitude, t.latitude, 1],
        })),
        ...scene.sites
          .filter((s) => s.position)
          .map((s) => ({
            id: s.development_key,
            position: [s.position!.longitude, s.position!.latitude, 1],
          })),
      ].filter((item) => item.id === scene.selected),
      getPosition: (d) => d.position as [number, number, number],
      getRadius: 28,
      radiusMinPixels: 16,
      filled: false,
      stroked: true,
      lineWidthMinPixels: 3,
      getLineColor: [20, 132, 155, 255],
    }),
  ];
}
function weatherLayers(scene: VisualScene): Layer[] {
  if (!scene.weatherVisible || scene.weather === 'sunny') return [];
  const clouds = Array.from({ length: 5 }, (_, i) => {
    const x =
      144.958 + (i % 3) * 0.004 + Math.sin(scene.clock / 600000 + i) * 0.0004;
    const y = -37.822 - Math.floor(i / 3) * 0.003;
    return [
      [-0.0006, 0, 32],
      [0, 0.0001, 44],
      [0.00055, 0, 32],
      [0, -0.0001, 38],
    ].map(([dx, dy, radius]) => ({
      position: [x + dx, y + dy, 150] as [number, number, number],
      radius,
    }));
  }).flat();
  const layers: Layer[] = [
    new ScatterplotLayer({
      id: 'demo-clouds',
      data: clouds,
      getPosition: (d) => d.position,
      getRadius: (d) => d.radius,
      getFillColor:
        scene.weather === 'rainy' ? [193, 203, 212, 150] : [235, 239, 244, 185],
      billboard: true,
      stroked: false,
    }),
  ];
  if (scene.weather === 'rainy') {
    const drops = Array.from({ length: 96 }, (_, i) => {
      const z = 150 - ((i * 37 + scene.clock / 30) % 140);
      const lon = 144.955 + (((i * 31) % 97) / 97) * 0.017,
        lat = -37.82 - (((i * 17) % 89) / 89) * 0.009;
      return {
        from: [lon, lat, z] as [number, number, number],
        to: [lon - 0.00004, lat + 0.000015, z - 10] as [number, number, number],
      };
    });
    layers.push(
      new LineLayer({
        id: 'demo-rain',
        data: drops,
        getSourcePosition: (d) => d.from,
        getTargetPosition: (d) => d.to,
        getColor: [65, 132, 189, 150],
        getWidth: 1.5,
      }),
    );
  }
  return layers;
}
export async function mountScene(
  map: Map,
  initial: VisualScene,
  signal: AbortSignal,
  ready: () => void,
  failed: () => void,
  buildingsReady: (available: boolean) => void,
) {
  let buildings: Mass[] = [];
  try {
    buildings = await loadBuildings(initial.buildingsUrl, initial.buildingHash);
    if (!signal.aborted) buildingsReady(true);
  } catch {
    if (!signal.aborted) buildingsReady(false);
  }
  if (signal.aborted) return null;
  let layers: Layer[] = [],
    announced = false;
  const drawnModels = new Set<string>();
  let requiredModels: string[] = [];
  const drawn = (id: string) => {
    drawnModels.add(id);
  };
  const overlay = new MapLibreOverlay({
    interleaved: true,
    onError: () => {
      if (!signal.aborted) failed();
    },
    onAfterRender: () => {
      if (
        !announced &&
        requiredModels.every((id) => drawnModels.has(id)) &&
        !signal.aborted
      ) {
        announced = true;
        ready();
      }
    },
    getTooltip: ({ object }) =>
      object?.label
        ? `Schedule simulation, not live · ${object.label}${object.demoDelay ? ` · ${object.demoDelay === 'severe' ? 'Severe demo delay' : 'Demo delay'}` : ''}`
        : object?.name
          ? `DAM status: ${object.status} · ${object.name}`
          : null,
  });
  const update = (scene: VisualScene) => {
    // Track rendered model identities, not the latest queued layer objects:
    // continuous Live updates may replace those before onAfterRender runs.
    requiredModels = [
      ...(scene.trams.length ? ['demo-trams'] : []),
      ...[true, false].flatMap((construction) =>
        scene.sites.some(
          (site) =>
            (site.status.toUpperCase() === 'UNDER CONSTRUCTION') ===
              construction &&
            site.position &&
            site.applicable,
        )
          ? [construction ? 'demo-cranes' : 'demo-planned']
          : [],
      ),
    ];
    layers = [
      ...(scene.buildingsVisible
        ? [
            new PolygonLayer<Mass>({
              id: 'demo-building-context',
              data: buildings,
              extruded: true,
              getPolygon: (b) => b.polygon,
              getElevation: (b) => b.top_m - b.base_m,
              getFillColor: [164, 173, 186, 95],
              opacity: 0.45,
              material: { ambient: 0.7, diffuse: 0.3, shininess: 0 },
            }),
          ]
        : []),
      ...modelLayers(scene, drawn),
      ...weatherLayers(scene),
    ];
    overlay.setProps({ layers });
  };
  const remove = () => {
    if (map.hasControl(overlay)) map.removeControl(overlay);
  };
  signal.addEventListener('abort', remove, { once: true });
  try {
    update(initial);
    map.addControl(overlay);
  } catch (error) {
    remove();
    throw error;
  }
  return update;
}
