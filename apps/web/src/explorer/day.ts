import type { Vehicle } from '../city';

export type SampleDay = 'today' | 'previous';
export const SAMPLE_DATES = {
  today: '8 October 2026',
  previous: '7 October 2026',
};
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
export const PREVIOUS_WEATHER: typeof WEATHER = [
  { at: 0, kind: 'cloudy', temperature: 12 },
  { at: 4, kind: 'rainy', temperature: 11 },
  { at: 6, kind: 'cloudy', temperature: 13 },
  { at: 8, kind: 'sunny', temperature: 17 },
  { at: 11, kind: 'sunny', temperature: 23 },
  { at: 13, kind: 'cloudy', temperature: 24 },
  { at: 15, kind: 'rainy', temperature: 19 },
  { at: 17, kind: 'rainy', temperature: 16 },
  { at: 19, kind: 'cloudy', temperature: 15 },
  { at: 20, kind: 'cloudy', temperature: 14 },
  { at: 22, kind: 'cloudy', temperature: 13 },
];
export function weatherReadings(day: SampleDay = 'today') {
  return day === 'previous' ? PREVIOUS_WEATHER : WEATHER;
}
export function weatherAt(ms: number, day: SampleDay = 'today') {
  const hour = clampClock(ms) / 3_600_000;
  return [...weatherReadings(day)]
    .reverse()
    .find((reading) => reading.at <= hour)!;
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
