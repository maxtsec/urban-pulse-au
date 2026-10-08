import type { Polygon, MultiPolygon } from 'geojson';
import type { DemoTram } from './day.ts';
import { inArea } from './schedule.ts';
import type { SampleDay } from './day.ts';
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
export const DEMO_COVERAGE_GAPS = [
  {
    area: 'cbd' as const,
    domain: 'transport' as const,
    start: minute(9, 40),
    end: minute(10, 5),
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
export function assessDemo(
  area: DemoArea,
  clock: number,
  day: SampleDay = 'today',
): DemoAssessment {
  if (!Number.isFinite(clock) || clock < 0 || clock > 86_400_000)
    throw new Error('Invalid demo clock');
  const reasons = demoReasons(day).filter(
    (r) => r.area === area && r.start <= clock && clock < r.end,
  );
  const missing: DemoDomain[] = demoGaps(day)
    .filter((gap) => gap.area === area && gap.start <= clock && clock < gap.end)
    .map((gap) => gap.domain);
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
  day: SampleDay = 'today',
): DemoReason | undefined {
  return demoReasons(day)
    .filter(
      (reason) =>
        reason.domain === 'transport' &&
        reason.area === area &&
        reason.start <= clock &&
        clock < reason.end &&
        Math.hypot(
          (longitude - reason.location[0]) * 88000,
          (latitude - reason.location[1]) * 111000,
        ) <= 650,
    )
    .sort(
      (a, b) =>
        Number(b.severity === 'severe') - Number(a.severity === 'severe'),
    )[0];
}

export function demoChanges(
  area: DemoArea,
  clock: number,
  day: SampleDay = 'today',
) {
  const times = [
    ...new Set([
      0,
      ...demoReasons(day)
        .filter((r) => r.area === area)
        .flatMap((r) => [r.start, r.end]),
      ...demoGaps(day)
        .filter((gap) => gap.area === area)
        .flatMap((gap) => [gap.start, gap.end]),
    ]),
  ].sort((a, b) => a - b);
  return {
    previous: times.filter((t) => t <= clock).at(-1) ?? 0,
    next: times.find((t) => t > clock) ?? null,
  };
}

const PREVIOUS_REASONS: readonly DemoReason[] = [
  {
    id: 'am-cbd',
    area: 'cbd',
    domain: 'transport',
    severity: 'affected',
    title: 'Morning service delays',
    detail:
      'Demo morning disruption near Swanston Street; scheduled movement is unchanged.',
    start: minute(7, 15),
    end: minute(8, 45),
    location: [144.9665, -37.8154],
  },
  {
    id: 'am-southbank',
    area: 'southbank',
    domain: 'transport',
    severity: 'affected',
    title: 'Local morning delays',
    detail: 'Authored delays near Queensbridge; not measured congestion.',
    start: minute(8),
    end: minute(9, 20),
    location: [144.9601, -37.8231],
  },
  {
    id: 'lunch-cbd',
    area: 'cbd',
    domain: 'transport',
    severity: 'severe',
    title: 'Midday service interruption',
    detail:
      'A short severe-delay demonstration. Map vehicles still follow the timetable.',
    start: minute(12, 10),
    end: minute(12, 35),
    location: [144.9665, -37.8154],
  },
  {
    id: 'pm-rain',
    area: 'southbank',
    domain: 'weather',
    severity: 'affected',
    title: 'Heavy-rain warning',
    detail: 'Synthetic warning over Southbank; no observed hazard is asserted.',
    start: minute(15),
    end: minute(17, 40),
    location: [144.963, -37.825],
  },
  {
    id: 'pm-cbd-rain',
    area: 'cbd',
    domain: 'weather',
    severity: 'affected',
    title: 'Heavy-rain warning',
    detail: 'Synthetic warning over CBD, independent of tram service coverage.',
    start: minute(15, 30),
    end: minute(17, 30),
    location: [144.9665, -37.8154],
  },
  {
    id: 'pm-southbank',
    area: 'southbank',
    domain: 'transport',
    severity: 'severe',
    title: 'Evening service delays',
    detail:
      'Authored peak-period interruption near Queensbridge; simulated positions remain on schedule.',
    start: minute(17),
    end: minute(18, 15),
    location: [144.9601, -37.8231],
  },
  {
    id: 'pm-cbd',
    area: 'cbd',
    domain: 'transport',
    severity: 'affected',
    title: 'Evening local delays',
    detail: 'Authored local tram delays, not an estimate from vehicle counts.',
    start: minute(17, 20),
    end: minute(18, 40),
    location: [144.9665, -37.8154],
  },
  {
    id: 'late-cbd',
    area: 'cbd',
    domain: 'transport',
    severity: 'affected',
    title: 'Late service delays',
    detail:
      'Authored late-evening service impact with recovery before midnight.',
    start: minute(22, 15),
    end: minute(23),
    location: [144.9665, -37.8154],
  },
];
const PREVIOUS_GAPS = [
  {
    area: 'cbd' as const,
    domain: 'transport' as const,
    start: minute(10, 15),
    end: minute(10, 45),
  },
  {
    area: 'southbank' as const,
    domain: 'transport' as const,
    start: minute(15, 45),
    end: minute(16, 15),
  },
  {
    area: 'southbank' as const,
    domain: 'transport' as const,
    start: minute(20),
    end: minute(20, 40),
  },
];
export const demoReasons = (day: SampleDay = 'today') =>
  day === 'previous' ? PREVIOUS_REASONS : DEMO_REASONS;
export const demoGaps = (day: SampleDay = 'today') =>
  day === 'previous' ? PREVIOUS_GAPS : DEMO_COVERAGE_GAPS;
export const healthMoments = (day: SampleDay = 'today') =>
  day === 'previous'
    ? [
        { label: 'Morning delays', at: minute(8, 15) },
        { label: 'Midday interruption', at: minute(12, 15) },
        { label: 'Rain + evening delays', at: minute(17, 25) },
        { label: 'Missing data', at: minute(20, 15) },
        { label: 'Recovered', at: minute(23, 30) },
      ]
    : HEALTH_MOMENTS;

export type DemoImpact = {
  affected: number | null;
  total: number | null;
  percent: number | null;
  reason: 'missing' | 'empty' | null;
};
/** Instantaneous sample share, not actual lateness or an interval average. */
export function demoImpact(
  trams: readonly DemoTram[],
  area: DemoArea,
  geometry: Polygon | MultiPolygon,
  clock: number,
  day: SampleDay = 'today',
): DemoImpact {
  if (assessDemo(area, clock, day).missing.includes('transport'))
    return { affected: null, total: null, percent: null, reason: 'missing' };
  const local = [
    ...new Map(
      trams
        .filter((t) => inArea([t.longitude, t.latitude], geometry))
        .map((t) => [t.id, t]),
    ).values(),
  ];
  const affected = local.filter((t) =>
    demoTramDelay(clock, t.longitude, t.latitude, area, day),
  ).length;
  return {
    affected,
    total: local.length,
    percent: local.length ? Math.round((affected / local.length) * 100) : null,
    reason: local.length ? null : 'empty',
  };
}
