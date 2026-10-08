import { fixtureTracks } from '../fixture-tracks.ts';
import { TramPath } from '../animation/tram-path.ts';
import type { Vehicle, Development } from '../city';

export const DAY_MS = 86_400_000;
export const WINDOW_MS = 7_200_000;
export const INITIAL_MS = 8 * 3_600_000;
export type WeatherKind = 'sunny' | 'cloudy' | 'rainy';
export type DemoTram = Vehicle & { heading: number; pair: [number, number] };
export const WEATHER: { at: number; kind: WeatherKind; temperature: number }[] =
  [
    { at: 0, kind: 'cloudy', temperature: 13 },
    { at: 6, kind: 'sunny', temperature: 17 },
    { at: 8.5, kind: 'cloudy', temperature: 19 },
    { at: 9, kind: 'rainy', temperature: 16 },
    { at: 11, kind: 'cloudy', temperature: 18 },
    { at: 13, kind: 'sunny', temperature: 23 },
    { at: 17, kind: 'cloudy', temperature: 20 },
    { at: 21, kind: 'rainy', temperature: 15 },
  ];
export const SITES: Development[] = [
  {
    development_key: 'demo-riverside',
    name: 'Riverside works',
    status: 'Under construction',
    clue_small_area: 'Southbank',
    position: { longitude: 144.9633, latitude: -37.8235 },
    year_completed: null,
    applicable: true,
  },
  {
    development_key: 'demo-gardens',
    name: 'Garden precinct',
    status: 'Under construction',
    clue_small_area: 'Southbank',
    position: { longitude: 144.9668, latitude: -37.8264 },
    year_completed: null,
    applicable: true,
  },
  {
    development_key: 'demo-square',
    name: 'Neighbourhood square',
    status: 'Planned',
    clue_small_area: 'Southbank',
    position: { longitude: 144.9588, latitude: -37.8247 },
    year_completed: null,
    applicable: true,
  },
];
const paths = fixtureTracks.features.map((track, index) => {
  const coordinates = track.geometry.coordinates;
  const distances = [0];
  for (let i = 1; i < coordinates.length; i++) {
    const [x, y] = coordinates[i];
    const [px, py] = coordinates[i - 1];
    distances.push(
      distances[i - 1] + Math.hypot((x - px) * 87900, (y - py) * 111320),
    );
  }
  return {
    path: new TramPath(`demo-${index}`, coordinates, distances),
    length: distances.at(-1)!,
  };
});
export type SyntheticObservation = { at: number; distance: number };
// Author the day's received samples once; frame rendering only reads a bracket.
const observations = Array.from({ length: 6 }, (_, index) =>
  Array.from({ length: DAY_MS / 60_000 + 1 }, (_, minute) => {
    const at = minute * 60_000;
    const phase = at + index * 120_000;
    const fraction = (phase % 600_000) / 600_000;
    return {
      at,
      distance:
        (Math.floor(phase / 600_000) % 2 === 0 ? fraction : 1 - fraction) *
        paths[index % paths.length].length,
    };
  }),
);
export function sampleDistance(
  display: number,
  a: SyntheticObservation,
  b: SyntheticObservation,
): number {
  if (a.at === b.at) return a.distance;
  const fraction = Math.max(0, Math.min(1, (display - a.at) / (b.at - a.at)));
  return a.distance + (b.distance - a.distance) * fraction;
}
export function clampClock(ms: number): number {
  if (!Number.isFinite(ms)) throw new Error('Invalid demo clock');
  return Math.max(0, Math.min(DAY_MS, Math.floor(ms)));
}
export function windowFor(ms: number): number {
  return Math.min(
    DAY_MS - WINDOW_MS,
    Math.floor(clampClock(ms) / WINDOW_MS) * WINDOW_MS,
  );
}
export function clockLabel(ms: number, seconds = false): string {
  const value = clampClock(ms),
    h = Math.floor(value / 3_600_000),
    m = Math.floor(value / 60_000) % 60,
    s = Math.floor(value / 1000) % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}${seconds ? `:${String(s).padStart(2, '0')}` : ''}`;
}
export function weatherAt(ms: number) {
  const hour = clampClock(ms) / 3_600_000;
  return [...WEATHER].reverse().find((reading) => reading.at <= hour)!;
}
/** Pure simulation: never an observed transport record or an area assessment. */
export function tramsAt(ms: number): DemoTram[] {
  const clock = clampClock(ms),
    display = Math.max(0, clock - 60_000);
  return Array.from({ length: 6 }, (_, index) => {
    const { path, length } = paths[index % paths.length];
    const sampleIndex = Math.floor(display / 60_000);
    const a = observations[index][sampleIndex];
    const next = observations[index][sampleIndex + 1];
    const b = clock < 60_000 ? a : next;
    const along = sampleDistance(display, a, b);
    const forward = next.distance > a.distance;
    const coordinate = path.at(along)!;
    const neighbour = path.at(
      Math.max(0, Math.min(length, along + (forward ? 1 : -1))),
    )!;
    const heading =
      (Math.atan2(
        (neighbour[0] - coordinate[0]) * 87900,
        (neighbour[1] - coordinate[1]) * 111320,
      ) *
        180) /
      Math.PI;
    return {
      id: `demo-tram-${index}`,
      label: `Tram ${index + 1}`,
      route_id: index % 2 ? 'B' : 'A',
      longitude: coordinate[0],
      latitude: coordinate[1],
      observed_at: null,
      freshness: 'current',
      visible_on_map: true,
      event_id: `sim-${index}`,
      revision: 0,
      capture_ids: [],
      heading,
      pair: [a.at, b.at],
    };
  });
}

export const LIVE_START_MS = 10 * 3_600_000;
export function liveEdgeAt(elapsedMs: number): number {
  return clampClock(LIVE_START_MS + Math.max(0, elapsedMs));
}
export function availableWindow(start: number, edge: number) {
  const end = clampClock(edge);
  const safeStart = Math.max(0, Math.min(clampClock(start), end));
  return { start: safeStart, end: Math.min(end, safeStart + WINDOW_MS) };
}
export function historyClock(requested: number, edge: number): number {
  return Math.min(clampClock(requested), clampClock(edge));
}
