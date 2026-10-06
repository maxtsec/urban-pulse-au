import { displayDateTime, displaySourceDate, displayTime } from './city';
import type { Snapshot } from './city';
import { conditionExplanation, coverageOf } from './conditions';
import { ReplayDiagnostics } from './ReplayDiagnostics';

type Props = {
  snapshot: Snapshot;
  onShowDevelopments: () => void;
};

export function AreaOverview({ snapshot, onShowDevelopments }: Props) {
  const coverage = (id: string) => coverageOf(snapshot, id);
  const weatherCoverage = coverage('weather_warnings');
  const reading = snapshot.weather?.reading;
  return (
    <section className="area-overview" aria-label="Area overview">
      <h2>Area conditions</h2>
      <p className="condition-explanation">{conditionExplanation(snapshot)}</p>
      {snapshot.assessment.reasons.map((reason) => (
        <div className="reason" key={reason.id}>
          <strong>{reason.reason}</strong>
          <span>
            Effective {displayTime(reason.effective_from)} ·{' '}
            {reason.resolved_at
              ? 'Resolved ' + displayTime(reason.resolved_at)
              : reason.effective_until
                ? 'Valid until ' + displayTime(reason.effective_until)
                : 'Resolution not yet observed'}
          </span>
        </div>
      ))}
      <div className="domain-row">
        <div>
          <h3>Transport</h3>
          <p>
            {coverage('transport_service') === 'error'
              ? 'Source unavailable · fixture'
              : snapshot.assessment.reasons.some(
                    (reason) => reason.input_id === 'transport_service',
                  )
                ? '1 service disruption · fixture'
                : 'No active disruption · fixture'}
          </p>
        </div>
        <span className={`status-pill ${coverage('transport_service')}`}>
          {coverage('transport_service')}
        </span>
      </div>
      <div className="domain-row">
        <div>
          <h3>Weather & hazards</h3>
          <p>
            {weatherCoverage === 'unknown'
              ? snapshot.weather
                ? 'Warning coverage incomplete'
                : 'Warning data not connected'
              : weatherCoverage === 'error'
                ? 'Warning source unavailable'
                : weatherCoverage === 'stale'
                  ? 'Warning coverage is stale'
                  : weatherCoverage === 'unsupported'
                    ? 'Warning coverage unsupported'
                    : 'Warning coverage current'}
          </p>
          {reading && (
            <p>
              Modelled for {displayDateTime(reading.valid_at)} ·{' '}
              <a href={reading.source_url}>Open-Meteo</a> · Informational only;
              separate from warning coverage.
            </p>
          )}
        </div>
        <span className={`status-pill ${weatherCoverage}`}>
          {weatherCoverage}
        </span>
      </div>
      <h3 className="profile-heading">Area profile</h3>
      <div className="domain-row">
        <div>
          <h3>Planning & infrastructure</h3>
          {snapshot.planning.records ? (
            <>
              <p>
                {snapshot.planning.records.length} located developments ·
                Synthetic sample
              </p>
              <p>As of {displaySourceDate(snapshot.planning.as_of)}</p>
              {(snapshot.planning.unlocated_records?.length ?? 0) > 0 && (
                <p>
                  {snapshot.planning.unlocated_records!.length} with unknown
                  location
                </p>
              )}
              <button className="text-button" onClick={onShowDevelopments}>
                View development activity
              </button>
            </>
          ) : (
            <>
              <p>Development data not connected</p>
              <p>As of: unknown</p>
            </>
          )}
        </div>
        <span className={`status-pill ${snapshot.planning.state}`}>
          {snapshot.planning.state}
        </span>
      </div>
      <a
        className="evidence-link"
        href={snapshot.evidence_url}
        target="_blank"
        rel="noreferrer"
      >
        View fixture evidence ↗
      </a>
      <details className="diagnostics">
        <summary>Replay diagnostics</summary>
        <ReplayDiagnostics label="Transport" counts={snapshot.projection} />
        {snapshot.weather && (
          <ReplayDiagnostics
            label="Weather"
            counts={snapshot.weather.projection}
          />
        )}
        {snapshot.planning.projection && (
          <ReplayDiagnostics
            label="Planning"
            counts={snapshot.planning.projection}
          />
        )}
        <p>Policy: {snapshot.policy_version}</p>
      </details>
    </section>
  );
}
