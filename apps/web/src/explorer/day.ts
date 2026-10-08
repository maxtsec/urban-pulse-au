import type { Vehicle } from '../city';

export const DAY_MS = 86_400_000;
export const WINDOW_MS = 7_200_000;
export const INITIAL_MS = 8 * 3_600_000;
export type WeatherKind = 'sunny' | 'cloudy' | 'rainy';
export type DemoTram = Vehicle & {
  heading: number;
  pair: [number, number];
  demoDelay?: 'affected' | 'severe';
};
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
