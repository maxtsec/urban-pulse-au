import type { Snapshot } from './city';

export function ReplayDiagnostics({
  label,
  counts,
}: {
  label: string;
  counts: Snapshot['projection'];
}) {
  return (
    <div role="group" aria-label={`${label} replay diagnostics`}>
      <h3>{label}</h3>
      <p>
        Applied {counts.apply} · Duplicates {counts.duplicate} · Superseded{' '}
        {counts.superseded} · Conflicts {counts.conflict} · Invalid{' '}
        {counts.rejected}
      </p>
    </div>
  );
}
