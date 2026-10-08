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
    // Two minute-spaced samples, received by clock. Trips reverse at sample boundaries.
    const phase = display + index * 120_000,
      trip = Math.floor(phase / 600_000),
      offset = phase % 600_000;
    const a = Math.floor(offset / 60_000) * 60_000,
      b = a + 60_000;
    const distance =
      ((a + (b - a) * ((offset - a) / (b - a))) / 600_000) * length;
    const forward = trip % 2 === 0,
      along = forward ? distance : length - distance;
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
      pair:
        clock < 60_000
          ? [0, 0]
          : [
              Math.max(0, display - offset + a),
              Math.max(0, display - offset + b),
            ],
    };
  });
}
