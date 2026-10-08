import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson';
import type { Map } from 'maplibre-gl';
import { MapLibreOverlay } from '@deck.gl/maplibre';
import { PolygonLayer } from '@deck.gl/layers';
import assetUrl from './assets/southbank-buildings.geojson?url';

export type Building = {
  structure_id: string;
  footprint_type: 'Structure';
  base_m: number;
  top_m: number;
  date_captured: string;
};
export type Mass = Building & { polygon: number[][][] };
let retained: Promise<Mass[]> | undefined;

/** Load once on demand; a failed fetch may be retried by switching back to 3D. */
export function loadBuildings(): Promise<Mass[]> {
  retained ??= fetch(assetUrl)
    .then(async (response) => {
      if (!response.ok) throw new Error('Building fixture unavailable');
      const data = (await response.json()) as FeatureCollection<
        Polygon | MultiPolygon,
        Building
      >;
      return data.features.flatMap(({ geometry, properties }) => {
        const polygons =
          geometry.type === 'Polygon'
            ? [geometry.coordinates]
            : geometry.coordinates;
        return polygons.map((polygon) => ({
          ...properties,
          polygon: polygon.map((ring) =>
            ring.map(([lng, lat]) => [lng, lat, properties.base_m]),
          ),
        }));
      });
    })
    .catch((error: unknown) => {
      retained = undefined;
      throw error;
    });
  return retained;
}

export async function addBuildings(
  map: Map,
  signal: AbortSignal,
  onError: () => void,
  onReady: () => void,
) {
  const data = await loadBuildings();
  if (signal.aborted) return;
  let painted = false;
  let errored = false;
  const overlay = new MapLibreOverlay({
    interleaved: true,
    onError: () => {
      errored = true;
      onError();
    },
    onAfterRender: () => {
      if (!painted && !errored && !signal.aborted) {
        painted = true;
        onReady();
      }
    },
    getTooltip: ({ object }: { object?: Mass }) =>
      object
        ? {
            text: `Observed · historical building ${object.structure_id}\nCaptured ${object.date_captured}\nBase ${object.base_m} m · top ${object.top_m} m\nCity of Melbourne · CC BY 4.0`,
          }
        : null,
    layers: [
      new PolygonLayer<Mass>({
        id: 'southbank-buildings',
        data,
        extruded: true,
        wireframe: true,
        pickable: true,
        getPolygon: (building) => building.polygon,
        // Vertex z is the component base; deck.gl adds this component's thickness.
        getElevation: (building) => building.top_m - building.base_m,
        getFillColor: [160, 167, 173, 125],
        getLineColor: [112, 120, 126, 120],
        opacity: 0.5,
        material: { ambient: 0.6, diffuse: 0.4, shininess: 0 },
      }),
    ],
  });
  const remove = () => {
    if (map.hasControl(overlay)) map.removeControl(overlay);
  };
  signal.addEventListener('abort', remove, { once: true });
  try {
    map.addControl(overlay);
  } catch (error) {
    remove();
    signal.removeEventListener('abort', remove);
    throw error;
  }
}
