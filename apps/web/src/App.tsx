import { useCallback, useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AREA_ID, displayTime, readJson } from './city';
import type { Snapshot } from './city';
import { CityMap } from './CityMap';
import type { Boundary } from './CityMap';

export function App() {
  const [seconds, setSeconds] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [scenario, setScenario] = useState('journey');
  const [selected, setSelected] = useState<string | null>(null);
  const [showVehicles, setShowVehicles] = useState(true);
  const [showBoundary, setShowBoundary] = useState(true);
  const result = useQuery({
    queryKey: ['city', scenario, seconds],
    queryFn: ({ signal }) =>
      readJson<Snapshot>(
        `/api/v1/areas/${AREA_ID}?seconds=${seconds}&scenario=${scenario}`,
        signal,
      ),
    retry: false,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
  const snapshot = result.data;
  const geometry = useQuery({
    queryKey: ['boundary', snapshot?.geometry_url],
    queryFn: ({ signal }) => readJson<Boundary>(snapshot!.geometry_url, signal),
    enabled: Boolean(snapshot),
    staleTime: Infinity,
    retry: false,
  });
  const selectVehicle = useCallback((id: string) => setSelected(id), []);

  useEffect(() => {
    if (!playing || !snapshot || result.isFetching || seconds >= 360) return;
    const timer = window.setTimeout(
      () => setSeconds((value) => Math.min(value + 15, 360)),
      2000,
    );
    return () => window.clearTimeout(timer);
  }, [playing, seconds, snapshot, result.isFetching]);

  const active = snapshot?.vehicles.find((vehicle) => vehicle.id === selected);
  const coverage = (id: string) =>
    snapshot?.assessment.coverage.find((item) => item.input_id === id)?.state ??
    'unknown';
  const condition = snapshot?.assessment.condition ?? 'unknown';

  function jump(value: number) {
    setPlaying(false);
    setSeconds(value);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="UrbanPulse home">
          <span className="brand-mark">
            u<span>p</span>
          </span>{' '}
          UrbanPulse<span className="brand-au">AU</span>
        </a>
        <span className="city-name">
          <span className="dot" /> Melbourne, Victoria
        </span>
        <span className="fixture-badge">SYNTHETIC DEMO · NO LIVE DATA</span>
      </header>
      <main>
        <section className="page-heading">
          <div>
            <p className="eyebrow">YOUR CITY, IN VIEW</p>
            <h1>A closer look at Southbank.</h1>
            <p className="subtitle">
              What’s happening now. What shapes this neighbourhood.
            </p>
          </div>
          <label className="area-picker">
            Explore an area
            <select aria-label="Area">
              <option>Southbank · CLUE area</option>
            </select>
          </label>
        </section>
        <section className="playback" aria-label="Fixture playback">
          <div>
            <p className="eyebrow">SCENARIO CLOCK</p>
            <strong data-testid="clock">
              {snapshot ? displayTime(snapshot.clock.at) : '—'}
            </strong>
            <span className="clock-date">4 Oct 2026 · Melbourne</span>
          </div>
          <div className="playback-controls">
            <button
              className="primary-button"
              onClick={() => {
                if (seconds >= 360) {
                  setSeconds(0);
                  setPlaying(true);
                } else {
                  setPlaying((value) => !value);
                }
              }}
              disabled={result.isError}
            >
              {playing && seconds < 360 ? 'Pause' : 'Play scenario'}
            </button>
            <button onClick={() => jump(0)}>Reset</button>
            <label className="timeline-label">
              Scenario time <output>{seconds}s</output>
              <input
                aria-label="Scenario time"
                type="range"
                min="0"
                max="360"
                step="15"
                value={seconds}
                onChange={(event) => jump(Number(event.target.value))}
              />
            </label>
            <label className="scenario-picker">
              Scenario
              <select
                aria-label="Scenario"
                value={scenario}
                onChange={(event) => {
                  setScenario(event.target.value);
                  setPlaying(false);
                  setSelected(null);
                }}
              >
                <option value="journey">Tram journey</option>
                <option value="empty">Empty transport</option>
                <option value="outage">Transport outage</option>
              </select>
            </label>
          </div>
        </section>
        {result.isPending && (
          <div className="notice" role="status">
            Loading city observations…
          </div>
        )}
        {result.isError && (
          <div className="notice error" role="alert">
            <strong>City snapshot unavailable</strong>
            <p>
              Start the local API and PostGIS, then try again. No current
              conditions can be shown.
            </p>
            <button onClick={() => result.refetch()}>Try again</button>
          </div>
        )}
        {snapshot && !result.isError && (
          <div className="city-grid">
            <section className="map-card">
              <div className="card-heading">
                <div>
                  <h2>Neighbourhood map</h2>
                  <p>Observed tram positions within the Southbank boundary</p>
                </div>
                <span className="count-chip">
                  {snapshot.vehicles.filter((v) => v.visible_on_map).length} on
                  map
                </span>
              </div>
              <div className="layer-controls">
                <label>
                  <input
                    type="checkbox"
                    checked={showVehicles}
                    onChange={(event) => setShowVehicles(event.target.checked)}
                  />{' '}
                  Tram positions
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={showBoundary}
                    onChange={(event) => setShowBoundary(event.target.checked)}
                  />{' '}
                  Area boundary
                </label>
                <span>No external map requests</span>
              </div>
              {geometry.data && (
                <CityMap
                  boundary={geometry.data}
                  vehicles={snapshot.vehicles}
                  selected={selected}
                  onSelect={selectVehicle}
                  showVehicles={showVehicles}
                  showBoundary={showBoundary}
                />
              )}
              {geometry.isPending && (
                <div className="map-placeholder" role="status">
                  Loading area boundary…
                </div>
              )}
              {geometry.isError && (
                <div className="map-placeholder" role="alert">
                  Boundary unavailable. Observations remain in the list.
                  <button onClick={() => geometry.refetch()}>
                    Retry boundary
                  </button>
                </div>
              )}
              <div className="map-footnote">
                Positions are synthetic observations. Marker movement does not
                imply a measured route between points.
              </div>
            </section>
            <aside className="area-panel" aria-label="Area overview">
              <p className="eyebrow">AREA OVERVIEW</p>
              <h2>Southbank</h2>
              <p className="area-description">
                Inner Melbourne · City of Melbourne
              </p>
              <div className={`condition-box ${condition}`} role="status">
                <span className="status-symbol">
                  {condition === 'degraded' ? '!' : '?'}
                </span>
                <div>
                  <p>Current conditions</p>
                  <strong>
                    {condition === 'degraded'
                      ? 'Degraded'
                      : condition === 'normal'
                        ? 'Normal'
                        : 'Unknown'}
                  </strong>
                </div>
              </div>
              <p className="condition-explanation">
                {snapshot.assessment.reasons.length
                  ? 'A confirmed transport disruption affects this area.'
                  : 'Weather coverage is missing, so an overall normal condition cannot be confirmed.'}
              </p>
              {snapshot.assessment.reasons.map((reason) => (
                <div className="reason" key={reason.id}>
                  <strong>{reason.reason}</strong>
                  <span>
                    Effective {displayTime(reason.effective_from)} · resolves{' '}
                    {displayTime(reason.resolved_at)}
                  </span>
                </div>
              ))}
              <div className="domain-row">
                <span className="domain-icon">↔</span>
                <div>
                  <h3>Transport</h3>
                  <p>
                    {coverage('transport_service') === 'error'
                      ? 'Source unavailable · fixture'
                      : snapshot.assessment.reasons.length
                        ? '1 service disruption · fixture'
                        : 'No active disruption · fixture'}
                  </p>
                </div>
                <span
                  className={`coverage-pill ${coverage('transport_service')}`}
                >
                  {coverage('transport_service')}
                </span>
              </div>
              <div className="domain-row">
                <span className="domain-icon">☁</span>
                <div>
                  <h3>Weather & hazards</h3>
                  <p>Warning data not connected</p>
                </div>
                <span className="coverage-pill">unknown</span>
              </div>
              <div className="profile-heading">LONGER-TERM AREA PROFILE</div>
              <div className="domain-row">
                <span className="domain-icon">▥</span>
                <div>
                  <h3>Planning & infrastructure</h3>
                  <p>Development data not connected</p>
                  <p>As of: unknown</p>
                </div>
              </div>
              <a
                className="evidence-link"
                href={snapshot.evidence_url}
                target="_blank"
                rel="noreferrer"
              >
                View fixture evidence ↗
              </a>
              <p className="small-note">
                Conditions and data coverage are separate. No numerical
                area-health score.
              </p>
            </aside>
            <section className="observations-card">
              <div className="card-heading">
                <div>
                  <h2>Tram observations</h2>
                  <p>
                    The same observations as the map, with source times and
                    last-known positions.
                  </p>
                </div>
                <span className="count-chip">
                  {snapshot.positions_total} in area
                </span>
              </div>
              {snapshot.vehicles.length === 0 && (
                <p className="empty-state">
                  No tram observations in this fixture view.
                </p>
              )}
              {snapshot.positions_truncated && (
                <p role="status">
                  Showing the first {snapshot.positions_limit} observations.
                  More positions exist.
                </p>
              )}
              <div className="tram-list">
                {snapshot.vehicles.map((vehicle) => (
                  <button
                    key={vehicle.id}
                    aria-label={`Select ${vehicle.label} in list`}
                    aria-pressed={selected === vehicle.id}
                    className={`tram-row ${selected === vehicle.id ? 'selected' : ''}`}
                    onClick={() => selectVehicle(vehicle.id)}
                  >
                    <span className="tram-list-icon">▥</span>
                    <span>
                      <strong>{vehicle.label}</strong>
                      <small>{vehicle.route_id ?? 'Route unknown'}</small>
                    </span>
                    <span className="observation-time">
                      {displayTime(vehicle.observed_at)}
                    </span>
                    <span className={`coverage-pill ${vehicle.freshness}`}>
                      {vehicle.freshness === 'expired'
                        ? 'last known'
                        : vehicle.freshness}
                    </span>
                  </button>
                ))}
              </div>
              <div className="selection-detail" aria-live="polite">
                {active ? (
                  <>
                    <strong>{active.label} selected</strong>
                    <span>
                      Observation: {displayTime(active.observed_at)} ·{' '}
                      {active.freshness}
                    </span>
                    <span>
                      Position: {active.latitude.toFixed(5)},{' '}
                      {active.longitude.toFixed(5)} · Revision {active.revision}
                    </span>
                    <small>
                      Event: {active.event_id} · Capture:{' '}
                      {active.capture_ids.join(', ')}
                    </small>
                  </>
                ) : (
                  <span>
                    {selected
                      ? 'The selected tram is outside this area at this time.'
                      : 'Select a tram on the map or in the list to inspect its observation.'}
                  </span>
                )}
              </div>
            </section>
            <section className="scenario-notes">
              <p className="eyebrow">EXPLORE THE SCENARIO</p>
              <h2>Watch the evidence change.</h2>
              <p>
                Skip to a moment, or play the six-minute fixture at an
                accelerated pace.
              </p>
              <div className="moments">
                <button onClick={() => jump(30)}>30s · Position update</button>
                <button onClick={() => jump(60)}>
                  60s · Service interruption
                </button>
                <button onClick={() => jump(150)}>150s · Stale position</button>
                <button onClick={() => jump(330)}>
                  330s · Last known only
                </button>
              </div>
              <details>
                <summary>Replay diagnostics</summary>
                <p>
                  Applied {snapshot.projection.apply} · Duplicates{' '}
                  {snapshot.projection.duplicate} · Superseded{' '}
                  {snapshot.projection.superseded} · Conflicts{' '}
                  {snapshot.projection.conflict} · Invalid{' '}
                  {snapshot.projection.rejected}
                </p>
                <p>Policy: {snapshot.policy_version}</p>
              </details>
            </section>
          </div>
        )}
        <footer>
          UrbanPulse AU{' '}
          <span>Transport · Weather & Hazards · Planning & Infrastructure</span>
        </footer>
      </main>
    </div>
  );
}
