import { displayTime } from './city';
import type { Development, Vehicle } from './city';

type Props = {
  tramId: string | null;
  tram: Vehicle | undefined;
  developmentId: string | null;
  development: Development | undefined;
  onClose: () => void;
};

/** The one floating detail card: whatever is selected on the map or in a list. */
export function SelectionCard({
  tramId,
  tram,
  developmentId,
  development,
  onClose,
}: Props) {
  if (!tramId && !developmentId) return null;
  return (
    <section
      className="selection-card"
      aria-label="Selection details"
      aria-live="polite"
    >
      <button
        className="icon-button close"
        aria-label="Clear selection"
        onClick={onClose}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path
            d="M5 5l10 10M15 5L5 15"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </button>
      {tramId &&
        (tram ? (
          <>
            <strong>{tram.label} selected</strong>
            <span>
              Observation: {displayTime(tram.observed_at)} · {tram.freshness}
            </span>
            <span>Route: {tram.route_id ?? 'unknown'}</span>
            <span>
              Position: {tram.latitude.toFixed(5)}, {tram.longitude.toFixed(5)}{' '}
              · Revision {tram.revision}
            </span>
            <small>
              Event: {tram.event_id} · Capture: {tram.capture_ids.join(', ')}
            </small>
          </>
        ) : (
          <span>The selected tram is outside this area at this time.</span>
        ))}
      {developmentId &&
        (development ? (
          <>
            <strong>{development.name}</strong>
            <span>
              Source status: {development.status} · Reported area:{' '}
              {development.clue_small_area ?? 'Unknown'}
            </span>
            <span>
              {development.year_completed === null
                ? 'Completion year unknown'
                : `Completion year: ${development.year_completed}`}
            </span>
            <span>
              {development.position
                ? `Position: ${development.position.latitude.toFixed(5)}, ${development.position.longitude.toFixed(5)}`
                : 'Position unknown'}
            </span>
            <small>
              Synthetic development record; not a real project claim.
            </small>
          </>
        ) : (
          <span>This development is no longer in the current area list.</span>
        ))}
    </section>
  );
}
