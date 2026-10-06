import type { Snapshot } from './city';

export type Moment = { seconds: number; label: string };

const weatherMoments: Moment[] = [
  { seconds: 30, label: 'Advice' },
  { seconds: 60, label: 'Watch and Act' },
  { seconds: 150, label: 'Cancelled' },
  { seconds: 180, label: 'Emergency Warning' },
  { seconds: 240, label: 'Expired, coverage stale' },
  { seconds: 270, label: 'Coverage restored' },
  { seconds: 330, label: 'Incomplete coverage' },
];

const transportMoments: Moment[] = [
  { seconds: 30, label: 'Position update' },
  { seconds: 60, label: 'Service interruption' },
  { seconds: 150, label: 'Stale position' },
  { seconds: 330, label: 'Last known only' },
];

const planningMoments: Moment[] = [
  { seconds: 120, label: 'Partial capture' },
  { seconds: 150, label: 'New planning snapshot' },
  { seconds: 240, label: 'Planning unavailable' },
  { seconds: 270, label: 'Planning recovered' },
];

// Captures after 120s fail in this scenario, so no snapshot or recovery is received.
const planningOutageMoments: Moment[] = [
  { seconds: 90, label: 'Last successful receipt' },
  { seconds: 120, label: 'Planning outage begins' },
  { seconds: 270, label: 'Still unavailable' },
];

/** Authored fixture moments within the API clock, merged when domains share a second. */
export function scenarioMoments(snapshot: Snapshot): Moment[] {
  const sources = [snapshot.weather ? weatherMoments : transportMoments];
  if (snapshot.planning.records)
    sources.push(
      snapshot.scenario === 'planning-outage'
        ? planningOutageMoments
        : planningMoments,
    );
  const merged = new Map<number, string[]>();
  for (const moment of sources.flat()) {
    if (moment.seconds > snapshot.clock.end_seconds) continue;
    merged.set(moment.seconds, [
      ...(merged.get(moment.seconds) ?? []),
      moment.label,
    ]);
  }
  return [...merged]
    .sort(([a], [b]) => a - b)
    .map(([seconds, labels]) => ({
      seconds,
      label: `${seconds}s · ${labels.join(' / ')}`,
    }));
}
