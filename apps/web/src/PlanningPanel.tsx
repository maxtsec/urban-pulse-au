import { displayDateTime, displaySourceDate } from './city';
import type { Development, PlanningProfile } from './city';

export function PlanningPanel({
  planning,
  selected,
  onSelect,
}: {
  planning: PlanningProfile;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const records = planning.records ?? [];
  const unlocated = planning.unlocated_records ?? [];
  const active = [...records, ...unlocated].find(
    (record) => record.development_key === selected,
  );
  const row = (record: Development) => (
    <button
      key={record.development_key}
      className="development-row"
      aria-label={`Inspect ${record.name} in list`}
      aria-pressed={selected === record.development_key}
      onClick={() => onSelect(record.development_key)}
    >
      <span>
        <strong>{record.name}</strong>
        <small>{record.development_key}</small>
      </span>
      <span className="development-status">{record.status}</span>
    </button>
  );
  return (
    <section
      className="planning-card"
      id="developments"
      aria-label="Planning details"
    >
      <div className="card-heading">
        <div>
          <h2>Development activity</h2>
          <p>Area profile · Synthetic DAM sample</p>
        </div>
        <span className={`coverage-pill ${planning.state}`}>
          {planning.state}
        </span>
      </div>
      <p>
        <strong>Snapshot as of {displaySourceDate(planning.as_of)}</strong>
      </p>
      <p>
        Last complete receipt:{' '}
        {displayDateTime(planning.last_successful_received_at ?? null)}
      </p>
      {planning.state !== 'current' && (
        <p className="planning-notice" role="status">
          {planning.state === 'error'
            ? 'Planning source unavailable. '
            : planning.state === 'stale'
              ? 'Planning coverage is stale. '
              : 'Planning coverage is incomplete or unknown. '}
          {planning.snapshot_id
            ? 'Showing the last complete snapshot; location gaps remain explicit.'
            : 'No complete snapshot received yet.'}
        </p>
      )}
      <div
        className="development-list"
        role="group"
        aria-label="Developments inside Southbank"
      >
        {records.map(row)}
        {records.length === 0 && (
          <p>
            {planning.snapshot_id
              ? 'No located developments inside Southbank in this fixture snapshot.'
              : 'Development information is unavailable.'}
          </p>
        )}
      </div>
      {unlocated.length > 0 && (
        <div
          className="unlocated-developments"
          role="group"
          aria-label="Developments with unknown location"
        >
          <h3>Location unknown</h3>
          <p>
            Excluded from the map and Southbank count; the source area label is
            not a spatial match.
          </p>
          {unlocated.map(row)}
        </div>
      )}
      <div className="planning-selection" aria-live="polite">
        {active ? (
          <>
            <strong>{active.name}</strong>
            <p>
              Source status: {active.status} · Reported area:{' '}
              {active.clue_small_area ?? 'Unknown'}
            </p>
            <p>
              {active.year_completed === null
                ? 'Completion year unknown'
                : `Completion year: ${active.year_completed}`}
            </p>
            <p>
              {active.position
                ? `Position: ${active.position.latitude.toFixed(5)}, ${active.position.longitude.toFixed(5)}`
                : 'Position unknown'}
            </p>
          </>
        ) : (
          <p>
            {selected
              ? 'This development is no longer in the current area list.'
              : 'Select a building on the map or in the list to inspect it.'}
          </p>
        )}
      </div>
      {(planning.removed_records?.length ?? 0) > 0 && (
        <details className="planning-history">
          <summary>
            No longer listed in this snapshot (
            {planning.removed_records!.length})
          </summary>
          <p>
            Absence does not establish cancellation or completion. Previous
            snapshots remain in retained evidence.
          </p>
          {planning.removed_records!.map((record) => (
            <p key={record.development_key}>
              <strong>{record.name}</strong> · Last listed as {record.status} ·{' '}
              {displaySourceDate(record.last_seen_as_of)}
            </p>
          ))}
        </details>
      )}
      <p>
        Major development context, not all development or roadworks. Status
        changes do not affect current area conditions.
      </p>
      {planning.attribution && (
        <p className="planning-credit">
          Field model:{' '}
          <a href={planning.attribution.source_url}>
            {planning.attribution.owner} Development Activity Monitor
          </a>{' '}
          · <a href={planning.attribution.licence_url}>CC BY 4.0</a>.{' '}
          {planning.attribution.modifications}.
        </p>
      )}
    </section>
  );
}
