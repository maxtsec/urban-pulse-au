import { useCallback, useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AREA_ID, displayTime, readJson } from './city';
import type { Snapshot, Warning } from './city';
import { CityMap } from './CityMap';
import { WeatherPanel } from './WeatherPanel';
import { WeatherSummary } from './WeatherSummary';
import { ScenarioPicker, initialScenario, scenarios } from './ScenarioPicker';
import { ReplayDiagnostics } from './ReplayDiagnostics';
import tramIcon from './assets/tram.svg';
import type { Boundary } from './CityMap';

const EMPTY_WARNINGS: Warning[] = [];

export function App() {
  const [seconds, setSeconds] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [scenario, setScenario] = useState(initialScenario);
  const [selected, setSelected] = useState<string | null>(null);
  const [showVehicles, setShowVehicles] = useState(true);
  const [showBoundary, setShowBoundary] = useState(true);
  const [showWarnings, setShowWarnings] = useState(true);
  const [showTracks, setShowTracks] = useState(true);
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
  const endSeconds = snapshot?.clock.end_seconds ?? 0;
  const geometry = useQuery({
    queryKey: ['boundary', snapshot?.geometry_url],
    queryFn: ({ signal }) => readJson<Boundary>(snapshot!.geometry_url, signal),
    enabled: Boolean(snapshot),
    staleTime: Infinity,
    retry: false,
  });
  useEffect(() => {
    function restoreScenario() {
      setScenario(initialScenario());
      setPlaying(false);
      setSelected(null);
    }
    window.addEventListener('popstate', restoreScenario);
    return () => window.removeEventListener('popstate', restoreScenario);
  }, []);

  const selectVehicle = useCallback((id: string) => setSelected(id), []);

  useEffect(() => {
    if (!playing || !snapshot || result.isFetching || seconds >= endSeconds)
      return;
    const timer = window.setTimeout(
      () => setSeconds((value) => Math.min(value + 15, endSeconds)),
      2000,
    );
    return () => window.clearTimeout(timer);
  }, [playing, seconds, snapshot, endSeconds, result.isFetching]);

  const active = snapshot?.vehicles.find((vehicle) => vehicle.id === selected);
  const coverage = (id: string) =>
    snapshot?.assessment.coverage.find((item) => item.input_id === id)?.state ??
    'unknown';
  const condition = snapshot?.assessment.condition ?? 'unknown';
  const missingCoverage = (snapshot?.assessment.incomplete_inputs ?? [])
    .map((id) => {
      const label =
        id === 'transport_service'
          ? 'Transport service'
          : id === 'weather_warnings'
            ? 'Weather warnings'
            : id;
      return (
        label +
        (coverage(id) === 'error'
          ? ' unavailable'
          : coverage(id) === 'stale'
            ? ' coverage stale'
            : ' coverage missing')
      );
    })
    .join('; ');

  function changeScenario(value: string) {
    if (value !== scenario) {
      const url = new URL(window.location.href);
      url.searchParams.set('scenario', value);
      window.history.pushState(null, '', url);
    }
    setScenario(value);
    setPlaying(false);
    setSelected(null);
  }

  function jump(value: number) {
    setPlaying(false);
    setSeconds(Math.max(0, Math.min(value, endSeconds)));
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="UrbanPulse home">
          UrbanPulse
        </a>
        <span className="city-name">Melbourne, Victoria</span>
        <span className="fixture-badge">SYNTHETIC DEMO · NO LIVE DATA</span>
      </header>
      <main>
        <section className="page-heading">
          <div>
            <h1>Southbank</h1>
            <p className="subtitle">Trams, conditions and area context.</p>
          </div>
          <p className="area-caption">City of Melbourne · CLUE area</p>
        </section>
        <ScenarioPicker value={scenario} onChange={changeScenario} />
        {snapshot && snapshot.scenario !== scenario && (
          <div className="notice" role="status">
            Loading scenario… Still showing{' '}
            {scenarios.find((item) => item.id === snapshot.scenario)?.label}.
          </div>
        )}
        {snapshot && !result.isError && (
          <WeatherSummary
            weather={snapshot.weather}
            onShowWeather={() => changeScenario('weather')}
          />
        )}
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
                if (seconds >= endSeconds) {
                  setSeconds(0);
                  setPlaying(true);
                } else {
                  setPlaying((value) => !value);
                }
              }}
              disabled={result.isError || result.isPlaceholderData || !snapshot}
            >
              {playing && seconds < endSeconds ? 'Pause' : 'Play scenario'}
            </button>
            <button onClick={() => jump(0)}>Reset</button>
            <label className="timeline-label">
              Scenario time <output>{seconds}s</output>
              <input
                aria-label="Scenario time"
                type="range"
                min="0"
                max={endSeconds}
                step="15"
                value={seconds}
                onChange={(event) => jump(Number(event.target.value))}
              />
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
          <div className="city-grid" aria-busy={result.isPlaceholderData}>
            <div className="main-column">
              <section className="map-card">
                <div className="card-heading">
                  <div>
                    <h2>Neighbourhood map</h2>
                  </div>
                  <span className="count-chip">
                    {snapshot.vehicles.filter((v) => v.visible_on_map).length}{' '}
                    on map
                  </span>
                </div>
                <div className="layer-controls">
                  <label>
                    <input
                      type="checkbox"
                      checked={showVehicles}
                      onChange={(event) =>
                        setShowVehicles(event.target.checked)
                      }
                    />{' '}
                    Tram positions
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={showBoundary}
                      onChange={(event) =>
                        setShowBoundary(event.target.checked)
                      }
                    />{' '}
                    Area boundary
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={showTracks}
                      onChange={(event) => setShowTracks(event.target.checked)}
                    />
                    Tracks (illustrative)
                  </label>
                  {snapshot.weather && (
                    <label>
                      <input
                        type="checkbox"
                        checked={showWarnings}
                        onChange={(event) =>
                          setShowWarnings(event.target.checked)
                        }
                      />{' '}
                      Warning areas
                    </label>
                  )}
                </div>
                {geometry.data && (
                  <CityMap
                    boundary={geometry.data}
                    vehicles={snapshot.vehicles}
                    selected={selected}
                    onSelect={selectVehicle}
                    showVehicles={showVehicles}
                    showBoundary={showBoundary}
                    showTracks={showTracks}
                    warnings={snapshot.weather?.warnings ?? EMPTY_WARNINGS}
                    showWarnings={showWarnings}
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
                  Tracks and trams are illustrative. Southbank boundary: City of
                  Melbourne.
                </div>
              </section>

              {snapshot.weather && <WeatherPanel weather={snapshot.weather} />}
              <section className="observations-card">
                <div className="card-heading">
                  <div>
                    <h2>Tram observations</h2>
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
                      <img className="tram-list-icon" src={tramIcon} alt="" />
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
                        {active.longitude.toFixed(5)} · Revision{' '}
                        {active.revision}
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
            </div>
            <div className="side-column">
              <aside className="area-panel" aria-label="Area overview">
                <h2>Area conditions</h2>
                <p className="area-description">
                  Southbank · City of Melbourne
                </p>
                <div className={`condition-box ${condition}`} role="status">
                  <span className="status-symbol">
                    {condition === 'degraded'
                      ? '!'
                      : condition === 'normal'
                        ? '✓'
                        : '?'}
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
                    ? 'Known transport disruptions or applicable warnings affect this area.'
                    : condition === 'unknown'
                      ? missingCoverage + '. Overall conditions remain unknown.'
                      : 'Required current-condition inputs are complete.'}
                </p>
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
                              (reason) =>
                                reason.input_id === 'transport_service',
                            )
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
                  <div>
                    <h3>Weather & hazards</h3>
                    <p>
                      {coverage('weather_warnings') === 'unknown'
                        ? snapshot.weather
                          ? 'Warning coverage incomplete'
                          : 'Warning data not connected'
                        : coverage('weather_warnings') === 'error'
                          ? 'Warning source unavailable'
                          : coverage('weather_warnings') === 'stale'
                            ? 'Warning coverage is stale'
                            : coverage('weather_warnings') === 'unsupported'
                              ? 'Warning coverage unsupported'
                              : 'Warning coverage current'}
                    </p>
                  </div>
                  <span
                    className={`coverage-pill ${coverage('weather_warnings')}`}
                  >
                    {coverage('weather_warnings')}
                  </span>
                </div>
                <div className="profile-heading">Area profile</div>
                <div className="domain-row">
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
              </aside>
              <section className="scenario-notes">
                <h2>Demo moments</h2>
                <p>Jump to a change in the six-minute scenario.</p>
                {snapshot.weather ? (
                  <div className="moments">
                    <button onClick={() => jump(30)}>30s · Advice</button>
                    <button onClick={() => jump(60)}>
                      60s · Watch and Act
                    </button>
                    <button onClick={() => jump(150)}>150s · Cancelled</button>
                    <button onClick={() => jump(180)}>
                      180s · Emergency Warning
                    </button>
                    <button onClick={() => jump(240)}>
                      240s · Expired, coverage stale
                    </button>
                    <button onClick={() => jump(270)}>
                      270s · Coverage restored
                    </button>
                    <button onClick={() => jump(330)}>
                      330s · Incomplete coverage
                    </button>
                  </div>
                ) : (
                  <div className="moments">
                    <button onClick={() => jump(30)}>
                      30s · Position update
                    </button>
                    <button onClick={() => jump(60)}>
                      60s · Service interruption
                    </button>
                    <button onClick={() => jump(150)}>
                      150s · Stale position
                    </button>
                    <button onClick={() => jump(330)}>
                      330s · Last known only
                    </button>
                  </div>
                )}
                <details>
                  <summary>Replay diagnostics</summary>
                  <ReplayDiagnostics
                    label="Transport"
                    counts={snapshot.projection}
                  />
                  {snapshot.weather && (
                    <ReplayDiagnostics
                      label="Weather"
                      counts={snapshot.weather.projection}
                    />
                  )}
                  <p>Policy: {snapshot.policy_version}</p>
                </details>
              </section>
            </div>
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
