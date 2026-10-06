import { displayDateTime } from './city';
import type { WeatherSnapshot } from './city';

export function WeatherPanel({ weather }: { weather: WeatherSnapshot }) {
  return (
    <section className="weather-card" aria-label="Weather details">
      <div className="panel-heading">
        <h2>Weather warnings</h2>
        <span className="panel-note">Synthetic fixture</span>
      </div>
      <div className="warning-heading">
        <h3>Warning coverage</h3>
        <span className={`status-pill ${weather.coverage}`}>
          {weather.coverage}
        </span>
      </div>
      <p className="weather-receipt">
        Last feed update received (fixture):{' '}
        <time>{displayDateTime(weather.last_feed_update_received_at)}</time>
      </p>
      <p className="weather-credit">
        {weather.attribution.owner} ·{' '}
        <a href={weather.attribution.notice_url}>EMV emergency-data notice</a> ·
        Authored warning examples
      </p>
      {weather.warnings.length === 0 && (
        <p>
          No warning records received. Check coverage before interpreting an
          empty list.
        </p>
      )}
      <div className="warning-list">
        {weather.warnings.map((warning) => (
          <article
            className="warning-row"
            key={warning.id}
            aria-label={warning.headline}
          >
            <div className="warning-heading">
              <h4>{warning.headline}</h4>
              <span className="status-pill">{warning.lifecycle}</span>
            </div>
            <p>
              <strong>{warning.level}</strong> ·{' '}
              {warning.applicable === null
                ? 'Area applicability unknown'
                : warning.applicable
                  ? 'Overlaps Southbank'
                  : 'Outside Southbank'}
            </p>
            {!warning.recognized && (
              <p>
                Unrecognised product or warning level; coverage cannot be
                confirmed.
              </p>
            )}
            {warning.level === 'Advice' && (
              <p>Informational warning; not a degradation reason.</p>
            )}
            <p>{warning.description}</p>
            <p>Updated {displayDateTime(warning.updated_at)}</p>
            <p>
              Valid {displayDateTime(warning.effective_from)} —{' '}
              {displayDateTime(warning.effective_until)}
            </p>
            <a href={warning.source_url}>Warning source: VicEmergency</a>
          </article>
        ))}
      </div>
      <p className="weather-note">
        Shaded polygons show authored warning applicability, not observed storm
        or flood impacts. This demo provides no live emergency information.
      </p>
    </section>
  );
}
