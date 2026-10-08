import { TramPath } from '../animation/tram-path.ts';
import type {
  Feature,
  FeatureCollection,
  LineString,
  Polygon,
  MultiPolygon,
} from 'geojson';
import type { Development } from '../city';
import type { DemoTram } from './day.ts';

export type Stop = [arrivalMs: number, departureMs: number, distance: number];
export type ScheduledTrip = {
  id: string;
  trip_id: string;
  service_date: string;
  route_id: string;
  route: string;
  headsign: string;
  shape: string;
  stops: Stop[];
};
export type SampleData = {
  display_tracks: FeatureCollection<LineString>;
  areas: FeatureCollection<
    Polygon | MultiPolygon,
    { area_id: 'cbd' | 'southbank'; name: string }
  >;
  focus_mask: Feature<Polygon | MultiPolygon>;
  boundary: Feature<
    Polygon | MultiPolygon,
    { provider: string; licence: string; source_url: string }
  >;
  schedule: {
    date: string;
    timezone: string;
    trips: ScheduledTrip[];
    shapes: Record<string, { coordinates: number[][]; distances: number[] }>;
  };
  developments: Development[];
  dam_date: string;
  roads: FeatureCollection<LineString>;
  water: FeatureCollection<Polygon | MultiPolygon>;
};

/** Published identical timestamps are an instantaneous transition, not an invented dwell. */
export function scheduledDistance(stops: Stop[], clock: number): number | null {
  if (
    !Number.isFinite(clock) ||
    clock < stops[0][0] ||
    clock >= stops.at(-1)![1]
  )
    return null;
  let low = 0,
    high = stops.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (stops[mid][0] <= clock) low = mid + 1;
    else high = mid;
  }
  const a = stops[low - 1],
    b = stops[low];
  if (clock <= a[1] || !b) return a[2];
  return a[2] + (b[2] - a[2]) * ((clock - a[1]) / (b[0] - a[1]));
}
function inRing(point: number[], ring: number[][]) {
  let inside = false;
  const [x, y] = point;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [a, b] = ring[i],
      [c, d] = ring[j];
    const cross = (x - a) * (d - b) - (y - b) * (c - a);
    if (
      Math.abs(cross) < 1e-12 &&
      x >= Math.min(a, c) &&
      x <= Math.max(a, c) &&
      y >= Math.min(b, d) &&
      y <= Math.max(b, d)
    )
      return true;
    if (b > y !== d > y && x < ((c - a) * (y - b)) / (d - b) + a)
      inside = !inside;
  }
  return inside;
}
export function inArea(
  point: number[],
  geometry: Polygon | MultiPolygon,
): boolean {
  const polygons =
    geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  return polygons.some(
    (p) => inRing(point, p[0]) && !p.slice(1).some((r) => inRing(point, r)),
  );
}
export function makeSchedule(data: SampleData) {
  const paths = new Map(
    Object.entries(data.schedule.shapes).map(([id, s]) => [
      id,
      new TramPath(id, s.coordinates, s.distances),
    ]),
  );
  const tracks = data.display_tracks;
  const at = (clock: number): DemoTram[] =>
    data.schedule.trips.flatMap((trip) => {
      const distance = scheduledDistance(trip.stops, clock);
      if (distance === null) return [];
      const path = paths.get(trip.shape)!;
      const p = path.at(distance);
      if (!p || !inArea(p, data.boundary.geometry)) return [];
      const neighbour = path.at(distance + 1) ?? p;
      const heading =
        (Math.atan2(
          (neighbour[0] - p[0]) * 87900,
          (neighbour[1] - p[1]) * 111320,
        ) *
          180) /
        Math.PI;
      return [
        {
          id: trip.id,
          label: `Route ${trip.route} · ${trip.headsign}`,
          route_id: trip.route,
          longitude: p[0],
          latitude: p[1],
          observed_at: null,
          freshness: 'unknown',
          visible_on_map: true,
          event_id: trip.id,
          revision: 0,
          capture_ids: [],
          heading,
          pair: [clock, clock],
        },
      ];
    });
  return { at, tracks };
}
