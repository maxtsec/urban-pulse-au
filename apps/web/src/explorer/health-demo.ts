/** Authored presentation events, never measurements or production area policy. */
export type DemoArea = 'cbd' | 'southbank';
export type DemoStatus = 'clear' | 'affected' | 'severe' | 'unknown';
export type DemoDomain = 'transport' | 'weather';
export type DemoReason = {
  id: string;
  area: DemoArea;
  domain: DemoDomain;
  severity: 'affected' | 'severe';
  title: string;
  detail: string;
  start: number;
  end: number;
  location: [number, number];
};
const minute = (hour: number, minutes = 0) => (hour * 60 + minutes) * 60_000;
export const DEMO_REASONS: readonly DemoReason[] = [
  {
    id: 'cbd-delays',
    area: 'cbd',
    domain: 'transport',
    severity: 'affected',
    title: 'Local tram delays',
    detail:
      'An authored service alert near Swanston Street. This is not measured road congestion.',
    start: minute(8, 15),
    end: minute(9, 25),
    location: [144.9665, -37.8154],
  },
  {
    id: 'southbank-rain',
    area: 'southbank',
    domain: 'weather',
    severity: 'affected',
    title: 'Heavy-rain warning',
    detail:
      'An authored warning affecting Southbank. Rain animation alone never changes area status.',
    start: minute(9),
    end: minute(9, 35),
    location: [144.963, -37.825],
  },
  {
    id: 'southbank-service',
    area: 'southbank',
    domain: 'transport',
    severity: 'severe',
    title: 'Severe tram delays',
    detail:
      'An authored severe-delay scenario near Queensbridge. Map vehicles continue to show the published timetable, not affected live operations.',
    start: minute(9, 10),
    end: minute(9, 25),
    location: [144.9601, -37.8231],
  },
];
export const HEALTH_MOMENTS = [
  { label: 'Calm', at: minute(8) },
  { label: 'Local impact', at: minute(8, 25) },
  { label: 'Major impact', at: minute(9, 15) },
  { label: 'Recovered', at: minute(9, 36) },
  { label: 'Missing data', at: minute(9, 50) },
] as const;
export const STATUS_PRESENTATION: Record<
  DemoStatus,
  { label: string; color: string; symbol: string }
> = {
  clear: { label: 'No known impacts', color: '#278474', symbol: '✓' },
  affected: { label: 'Local impacts', color: '#b57919', symbol: '!' },
  severe: { label: 'Major disruption', color: '#be454d', symbol: '!' },
  unknown: { label: 'Data incomplete', color: '#74818b', symbol: '?' },
};
export const AREA_NAMES: Record<DemoArea, string> = {
  cbd: 'CBD',
  southbank: 'Southbank',
};
export const AREA_CENTRES: Record<DemoArea, [number, number]> = {
  cbd: [144.9635, -37.8138],
  southbank: [144.963, -37.825],
};
export type DemoAssessment = {
  area: DemoArea;
  status: DemoStatus;
  reasons: DemoReason[];
  missing: DemoDomain[];
};
export function assessDemo(area: DemoArea, clock: number): DemoAssessment {
  if (!Number.isFinite(clock) || clock < 0 || clock > 86_400_000)
    throw new Error('Invalid demo clock');
  const reasons = DEMO_REASONS.filter(
    (r) => r.area === area && r.start <= clock && clock < r.end,
  );
  const missing: DemoDomain[] =
    area === 'cbd' && clock >= minute(9, 40) && clock < minute(10, 5)
      ? ['transport']
      : [];
  const status = demoStatus(reasons, missing);
  return {
    area,
    status,
    reasons: [...reasons].sort(
      (a, b) =>
        Number(b.severity === 'severe') - Number(a.severity === 'severe') ||
        a.id.localeCompare(b.id),
    ),
    missing,
  };
}
export function demoStatus(
  reasons: readonly DemoReason[],
  missing: readonly DemoDomain[],
): DemoStatus {
  return reasons.some((r) => r.severity === 'severe')
    ? 'severe'
    : reasons.length
      ? 'affected'
      : missing.length
        ? 'unknown'
        : 'clear';
}

/** A deliberately authored 650 m demo zone; not inferred from scheduled speed. */
export function demoTramDelay(
  clock: number,
  longitude: number,
  latitude: number,
  area: DemoArea,
): DemoReason | undefined {
  return DEMO_REASONS.filter(
    (reason) =>
      reason.domain === 'transport' &&
      reason.area === area &&
      reason.start <= clock &&
      clock < reason.end &&
      Math.hypot(
        (longitude - reason.location[0]) * 88000,
        (latitude - reason.location[1]) * 111000,
      ) <= 650,
  ).sort(
    (a, b) => Number(b.severity === 'severe') - Number(a.severity === 'severe'),
  )[0];
}

export function demoChanges(area: DemoArea, clock: number) {
  const times = [
    ...new Set([
      0,
      ...DEMO_REASONS.filter((r) => r.area === area).flatMap((r) => [
        r.start,
        r.end,
      ]),
      ...(area === 'cbd' ? [minute(9, 40), minute(10, 5)] : []),
    ]),
  ].sort((a, b) => a - b);
  return {
    previous: times.filter((t) => t <= clock).at(-1) ?? 0,
    next: times.find((t) => t > clock) ?? null,
  };
}
