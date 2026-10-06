import { displayTime } from './city';
import type { Snapshot } from './city';
import tramIcon from './assets/tram.svg';

type Props = {
  snapshot: Snapshot;
  selected: string | null;
  onSelect: (id: string) => void;
};

export function TramList({ snapshot, selected, onSelect }: Props) {
  return (
    <section className="tram-observations" aria-label="Tram observations">
      <p className="panel-intro">
        {snapshot.positions_total} synthetic observations in Southbank. Select
        one to inspect it on the map.
      </p>
      {snapshot.vehicles.length === 0 && (
        <p className="empty-state">
          No tram observations in this fixture view.
        </p>
      )}
      {snapshot.positions_truncated && (
        <p role="status">
          Showing the first {snapshot.positions_limit} observations. More
          positions exist.
        </p>
      )}
      <div className="tram-list">
        {snapshot.vehicles.map((vehicle) => (
          <button
            key={vehicle.id}
            aria-label={`Select ${vehicle.label} in list`}
            aria-pressed={selected === vehicle.id}
            className={`list-row tram-row ${selected === vehicle.id ? 'selected' : ''}`}
            onClick={() => onSelect(vehicle.id)}
          >
            <img className="tram-list-icon" src={tramIcon} alt="" />
            <span className="row-main">
              <strong>{vehicle.label}</strong>
              <small>{vehicle.route_id ?? 'Route unknown'}</small>
            </span>
            <span className="observation-time">
              {displayTime(vehicle.observed_at)}
            </span>
            <span className={`status-pill ${vehicle.freshness}`}>
              {vehicle.freshness === 'expired'
                ? 'last known'
                : vehicle.freshness}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
