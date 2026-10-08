import { DAY_MS, WEATHER } from './day.ts';
import {
  DEMO_REASONS,
  DEMO_COVERAGE_GAPS,
  demoStatus,
  AREA_NAMES,
} from './health-demo.ts';
import type { DemoArea } from './health-demo.ts';
export type DaySegment = {
  start: number;
  end: number;
  tone: string;
  label: string;
  detail: string;
};
export type DayRow = {
  id: string;
  label: string;
  kind: 'health' | 'weather' | 'works';
  area?: DemoArea;
  segments: DaySegment[];
};
/** Half-open known history only. Never expose a later scripted endpoint in Live. */
export function dayRows(
  edge: number,
  constructionCount: number,
  damDate: string,
): DayRow[] {
  if (!Number.isFinite(edge) || edge < 0 || edge > DAY_MS)
    throw new Error('Invalid live edge');
  const traffic: DayRow[] = (['cbd', 'southbank'] as const).map((area) => {
    const reasons = DEMO_REASONS.filter(
      (r) => r.area === area && r.domain === 'transport',
    );
    const gaps = DEMO_COVERAGE_GAPS.filter(
      (g) => g.area === area && g.domain === 'transport',
    );
    const bounds = [
      ...new Set(
        [
          0,
          edge,
          ...reasons.flatMap((r) => [r.start, r.end]),
          ...gaps.flatMap((g) => [g.start, g.end]),
        ].filter((t) => t >= 0 && t <= edge),
      ),
    ].sort((a, b) => a - b);
    return {
      id: area,
      label: `${AREA_NAMES[area]} trams`,
      kind: 'health',
      area,
      segments: bounds.slice(0, -1).map((start, i) => {
        const active = reasons.filter((r) => r.start <= start && start < r.end);
        const missing = gaps.some((g) => g.start <= start && start < g.end);
        const tone = demoStatus(active, missing ? ['transport'] : []);
        const label =
          tone === 'clear'
            ? 'No demo delays'
            : tone === 'unknown'
              ? 'Data missing'
              : tone === 'severe'
                ? 'Severe delay'
                : 'Local delay';
        return {
          start,
          end: bounds[i + 1],
          tone,
          label,
          detail:
            active.map((r) => r.title).join(' · ') ||
            (missing
              ? 'Transport coverage missing'
              : 'No known transport impact in the demo'),
        };
      }),
    };
  });
  const weather: DayRow = {
    id: 'weather',
    label: 'Weather',
    kind: 'weather',
    segments: WEATHER.flatMap((reading, i) => {
      const start = reading.at * 3600000,
        end = Math.min(edge, (WEATHER[i + 1]?.at ?? 24) * 3600000);
      return start < end
        ? [
            {
              start,
              end,
              tone: reading.kind,
              label: `${reading.kind} · ${reading.temperature}°`,
              detail: 'Synthetic weather; rain alone does not imply a warning',
            },
          ]
        : [];
    }),
  };
  const works: DayRow = {
    id: 'works',
    label: 'Development',
    kind: 'works',
    segments:
      edge > 0
        ? [
            {
              start: 0,
              end: edge,
              tone: 'snapshot',
              label: `${constructionCount} DAM construction-status projects`,
              detail: `Fixed DAM snapshot ${damDate.slice(0, 10)}. Status only; working hours and actual on-site activity are unknown.`,
            },
          ]
        : [],
  };
  return [...traffic, weather, works];
}
