import { useCallback, useEffect, useMemo, useState } from 'react';
import { CityMap } from '../CityMap';
import type { Boundary } from '../CityMap';
import boundaryFeature from '../assets/southbank-boundary.json';
import { useReducedMotion } from '../useReducedMotion';
import {
  WINDOW_MS,
  SITES,
  WEATHER,
  clockLabel,
  tramsAt,
  weatherAt,
} from './day';
import type { VisualScene } from './scene';
import './explorer.css';
import { useDayPlayback } from './useDayPlayback';

const boundary: Boundary = {
  revision: 'synthetic-preview-boundary',
  feature: boundaryFeature as Boundary['feature'],
};
const emptyWarnings: [] = [];
const icons = { sunny: '☀', cloudy: '☁', rainy: '☂' };

export function Explorer() {
  const reduced = useReducedMotion();
  const playback = useDayPlayback(reduced);
  const {
    clock,
    edge,
    mode,
    playing,
    speed,
    setSpeed,
    seek,
    goLive,
    chooseWindow,
    togglePlay,
  } = playback;
  const windowStart = playback.window.start,
    windowEnd = playback.window.end;
  const [threeD, setThreeD] = useState(false);
  const [selected, select] = useState<string | null>(null);
  const [detail, setDetail] = useState<
    'health' | 'trams' | 'works' | 'weather'
  >('health');
  const [showLayers, setShowLayers] = useState(false);
  const [layers, setLayers] = useState({
    buildings: true,
    trams: true,
    works: true,
    weather: true,
    tracks: true,
  });
  const trams = useMemo(() => tramsAt(clock), [clock]);
  const weather = weatherAt(clock);
  const selectItem = useCallback((id: string) => {
    select(id);
    setDetail(id.startsWith('demo-tram') ? 'trams' : 'works');
  }, []);
  const scene: VisualScene = useMemo(
    () => ({
      trams: layers.trams ? trams : [],
      sites: layers.works ? SITES : [],
      clock: reduced ? Math.floor(clock / 60000) * 60000 : clock,
      weather: weather.kind,
      weatherVisible: layers.weather,
      buildingsVisible: layers.buildings,
      selected,
      select: selectItem,
    }),
    [trams, layers, clock, reduced, weather.kind, selected, selectItem],
  );
  const [wide, setWide] = useState(() => window.innerWidth > 900);
  useEffect(() => {
    const query = window.matchMedia('(min-width: 901px)');
    const update = () => setWide(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  const insets = useMemo(
    () =>
      wide
        ? { top: 105, right: 55, bottom: 210, left: 40 }
        : { top: 110, right: 40, bottom: 220, left: 24 },
    [wide],
  );
  const selectedTram = trams.find((t) => t.id === selected),
    selectedSite = SITES.find((s) => s.development_key === selected);
  return (
    <div className="explorer-shell">
      <header className="explorer-header">
        <a href="/" className="explorer-brand">
          UrbanPulse<span>Melbourne</span>
        </a>
        <span className="demo-pill">
          <i />
          Synthetic · 8 Oct 2026
        </span>
      </header>
      <main className="explorer-stage">
        <div className="explorer-viewport">
          <CityMap
            boundary={boundary}
            vehicles={trams}
            selected={selectedTram?.id ?? null}
            onSelect={selectItem}
            showVehicles={layers.trams}
            showBoundary={false}
            showTracks={layers.tracks}
            warnings={emptyWarnings}
            showWarnings={false}
            developments={SITES}
            showPlanning={layers.works}
            selectedDevelopment={selectedSite?.development_key ?? null}
            onSelectDevelopment={selectItem}
            insets={insets}
            glideMs={0}
            threeDimensional={threeD}
            showBuildings={layers.buildings}
            visualScene={scene}
          />
          {threeD && layers.weather && (
            <div
              className={`weather-atmosphere ${weather.kind}`}
              aria-hidden="true"
            />
          )}
          <div className="explorer-top">
            <div className="place-heading">
              <span>YOUR CITY, AT A GLANCE</span>
              <h1>Southbank</h1>
              <p>
                {mode === 'live'
                  ? 'Following simulated time'
                  : 'Explore a day in the city'}
              </p>
            </div>
            <div className="view-tools glass">
              <button aria-pressed={!threeD} onClick={() => setThreeD(false)}>
                2D
              </button>
              <button aria-pressed={threeD} onClick={() => setThreeD(true)}>
                3D
              </button>
              <button
                aria-expanded={showLayers}
                onClick={() => setShowLayers(!showLayers)}
              >
                Layers
              </button>
            </div>
          </div>
          {showLayers && (
            <section className="explorer-layers glass" aria-label="Map layers">
              {(Object.keys(layers) as (keyof typeof layers)[]).map((key) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={layers[key]}
                    onChange={(e) =>
                      setLayers({ ...layers, [key]: e.target.checked })
                    }
                  />
                  {key}
                </label>
              ))}
              <p>Models and weather effects appear in 3D.</p>
            </section>
          )}
          <div className="explorer-legend glass">
            <span>
              <i className="teal" />
              Simulated trams
            </span>
            <span>
              <i className="amber" />
              Illustrative works
            </span>
            {threeD && <span>Historical buildings</span>}
          </div>
          <section className="day-player glass" aria-label="Day playback">
            <div className="player-heading">
              <button
                className={`live-control ${mode === 'live' ? 'at-live' : ''}`}
                aria-label="Go live"
                aria-pressed={mode === 'live'}
                onClick={goLive}
              >
                <i />
                LIVE
              </button>
              <span className="player-context">
                {mode === 'live'
                  ? 'Simulated live · 1×'
                  : `${clockLabel(Math.max(0, edge - clock), true)} behind live`}
              </span>
              <span className="day-help">Today · 8 October</span>
            </div>
            <div className="playback-line">
              <button
                className="play-toggle"
                aria-label={
                  mode === 'live' || playing ? 'Pause demo' : 'Play demo'
                }
                disabled={reduced && mode !== 'live'}
                onClick={togglePlay}
              >
                {mode === 'live' || playing ? 'Ⅱ' : '▶'}
              </button>
              <output className="day-clock" data-testid="day-clock">
                {clockLabel(clock, true)}
              </output>
              <div className="day-range">
                <input
                  style={{
                    background: `linear-gradient(to right, #bd5d61 0%, #bd5d61 ${windowEnd > windowStart ? Math.max(0, (clock - windowStart) / (windowEnd - windowStart)) * 100 : 100}%, #d7dfe3 0%)`,
                  }}
                  aria-label="History time"
                  type="range"
                  min={windowStart}
                  max={windowEnd}
                  step={1000}
                  value={clock}
                  onChange={(e) => seek(Number(e.target.value))}
                />
                <div className="even-ticks">
                  {Array.from({ length: 5 }, (_, i) => (
                    <span key={i}>
                      {clockLabel(
                        windowStart + (i * (windowEnd - windowStart)) / 4,
                      )}
                    </span>
                  ))}
                </div>
              </div>
              <label className="speed-label">
                Speed
                <select
                  aria-label="Playback speed"
                  value={speed}
                  disabled={mode === 'live'}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                >
                  {[1, 7.5, 30, 120, 300].map((rate) => (
                    <option key={rate} value={rate}>
                      {rate}×
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div
              className="day-windows"
              role="group"
              aria-label="Choose two-hour window"
            >
              {Array.from({ length: 12 }, (_, i) => i * WINDOW_MS).map(
                (start) => (
                  <button
                    key={start}
                    aria-label={`${clockLabel(start)} to ${clockLabel(start + WINDOW_MS)}`}
                    disabled={start >= edge}
                    aria-pressed={clock >= start && clock < start + WINDOW_MS}
                    onClick={() => chooseWindow(start)}
                  >
                    <span>{clockLabel(start)}</span>
                    <i
                      className={
                        start < edge ? weatherAt(start).kind : 'future'
                      }
                    />
                  </button>
                ),
              )}
            </div>
            <div className="player-footnote">
              <span>
                {reduced
                  ? 'Reduced motion · use the time slider'
                  : mode === 'live'
                    ? 'Live follows a simulated clock. No live feeds connected.'
                    : 'Today’s history · future times are unavailable'}
              </span>
              <span>Sunny · Cloudy · Rainy</span>
            </div>
          </section>
        </div>
        <aside className="explorer-details glass" aria-label="Area information">
          <div className="detail-heading">
            <div>
              <span className="panel-eyebrow">AREA INFORMATION</span>
              <h2>Southbank</h2>
            </div>
            <span className="panel-clock">{clockLabel(clock)}</span>
          </div>
          <div
            className="info-tabs"
            role="tablist"
            aria-label="Area information pages"
          >
            {(
              [
                { id: 'health', label: 'Area health' },
                { id: 'weather', label: 'Weather' },
                { id: 'trams', label: 'Trams' },
                { id: 'works', label: 'Works' },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                role="tab"
                aria-selected={detail === tab.id}
                aria-controls="information-content"
                tabIndex={detail === tab.id ? 0 : -1}
                onClick={() => setDetail(tab.id)}
                onKeyDown={(event) => {
                  const tabs = ['health', 'weather', 'trams', 'works'] as const;
                  let index = tabs.indexOf(detail);
                  if (event.key === 'ArrowRight') index = (index + 1) % 4;
                  else if (event.key === 'ArrowLeft') index = (index + 3) % 4;
                  else if (event.key === 'Home') index = 0;
                  else if (event.key === 'End') index = 3;
                  else return;
                  event.preventDefault();
                  setDetail(tabs[index]);
                  document.getElementById(`tab-${tabs[index]}`)?.focus();
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <section
            className="information-content"
            id="information-content"
            role="tabpanel"
            aria-labelledby={`tab-${detail}`}
          >
            {detail === 'health' && (
              <>
                <div className="health-status">
                  <span>AREA HEALTH</span>
                  <h3>Not assessed</h3>
                  <p>Real source coverage is not connected yet.</p>
                </div>
                <h4>Data coverage</h4>
                <ul className="coverage-list">
                  <li>
                    <span>Transport</span>
                    <strong>Synthetic</strong>
                  </li>
                  <li>
                    <span>Weather</span>
                    <strong>Synthetic</strong>
                  </li>
                  <li>
                    <span>Planning</span>
                    <strong>Synthetic</strong>
                  </li>
                </ul>
                <p>No health rating until real coverage is available.</p>
              </>
            )}
            {detail === 'trams' && (
              <>
                <p>Simulated movement · 6 trams</p>
                {trams.map((tram) => (
                  <button
                    className="detail-row"
                    key={tram.id}
                    aria-pressed={selected === tram.id}
                    onClick={() => select(tram.id)}
                  >
                    <span className="glance-dot teal" />
                    {tram.label}
                    <small>Track {tram.route_id}</small>
                  </button>
                ))}
              </>
            )}
            {detail === 'works' && (
              <>
                <p>
                  Illustrative projects. Construction does not imply disruption.
                </p>
                {SITES.map((site) => (
                  <button
                    className="detail-row"
                    key={site.development_key}
                    aria-pressed={selected === site.development_key}
                    onClick={() => select(site.development_key)}
                  >
                    {site.name}
                    <small>{site.status}</small>
                  </button>
                ))}
              </>
            )}
            {detail === 'weather' && (
              <>
                <div className="weather-current">
                  <span className={`glance-icon ${weather.kind}`}>
                    {icons[weather.kind]}
                  </span>
                  <div>
                    <h3>{weather.temperature}°</h3>
                    <span className="weather-name">{weather.kind}</span>
                  </div>
                </div>
                <p>Synthetic weather · today’s readings</p>
                {WEATHER.filter(
                  (reading) => reading.at * 3600000 <= Math.min(clock, edge),
                ).map((reading) => (
                  <button
                    key={reading.at}
                    className="detail-row"
                    onClick={() => {
                      chooseWindow(
                        Math.floor((reading.at * 3600000) / WINDOW_MS) *
                          WINDOW_MS,
                        reading.at * 3600000,
                      );
                    }}
                  >
                    <span>
                      {icons[reading.kind]} {clockLabel(reading.at * 3600000)}
                    </span>
                    <small>
                      {reading.kind} · {reading.temperature}°
                    </small>
                  </button>
                ))}
              </>
            )}
          </section>
        </aside>
      </main>
    </div>
  );
}
