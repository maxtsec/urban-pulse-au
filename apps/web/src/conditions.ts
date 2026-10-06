import type { Snapshot } from './city';

export function coverageOf(snapshot: Snapshot, inputId: string) {
  return (
    snapshot.assessment.coverage.find((item) => item.input_id === inputId)
      ?.state ?? 'unknown'
  );
}

export function conditionLabel(condition: Snapshot['assessment']['condition']) {
  return condition === 'degraded'
    ? 'Degraded'
    : condition === 'normal'
      ? 'Normal'
      : 'Unknown';
}

/** Names every incomplete required input; an unknown overall state is never left unexplained. */
export function missingCoverage(snapshot: Snapshot) {
  return snapshot.assessment.incomplete_inputs
    .map((id) => {
      const label =
        id === 'transport_service'
          ? 'Transport service'
          : id === 'weather_warnings'
            ? 'Weather warnings'
            : id;
      const state = coverageOf(snapshot, id);
      return (
        label +
        (state === 'error'
          ? ' unavailable'
          : state === 'stale'
            ? ' coverage stale'
            : ' coverage missing')
      );
    })
    .join('; ');
}

export function conditionExplanation(snapshot: Snapshot) {
  if (snapshot.assessment.reasons.length)
    return 'Known transport disruptions or applicable warnings affect this area.';
  if (snapshot.assessment.condition === 'unknown')
    return missingCoverage(snapshot) + '. Overall conditions remain unknown.';
  return 'Required current-condition inputs are complete.';
}
