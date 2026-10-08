import { useCallback, useEffect, useMemo, useState } from 'react';
import { CityMap } from '../CityMap';
import type { Boundary } from '../CityMap';
import { makeSchedule } from './schedule';
import type { LoadedSample } from './sample';
import { useReducedMotion } from '../useReducedMotion';
import { WINDOW_MS, WEATHER, clockLabel, weatherAt } from './day';
import type { VisualScene } from './scene';
import './explorer.css';
import { useDayPlayback } from './useDayPlayback';

const emptyWarnings: [] = [];
const icons = { sunny: '☀', cloudy: '☁', rainy: '☂' };

export function Explorer({ sample }: { sample: LoadedSample }) {
  const { data, manifest } = sample;
  const boundary: Boundary = useMemo(
    () => ({ revision: manifest.version, feature: data.boundary }),
    [data, manifest],
  );
  const schedule = useMemo(() => makeSchedule(data), [data]);
  const sites = data.developments;
  const mapSites = useMemo(
    () => sites.filter((site) => site.status.toUpperCase() !== 'COMPLETED'),
    [sites],
  );
  const localContext = useMemo(
    () => ({ tracks: schedule.tracks, roads: data.roads, water: data.water }),
    [schedule, data],
  );
  const [credits, setCredits] = useState(false);
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
  const trams = useMemo(() => schedule.at(clock), [clock, schedule]);
  const weather = weatherAt(clock);
  const selectItem = useCallback((id: string) => {
    select(id);
    setDetail(id.startsWith('schedule:') ? 'trams' : 'works');
  }, []);
  const scene: VisualScene = useMemo(
    () => ({
      trams: layers.trams ? trams : [],
      sites: layers.works ? mapSites : [],
      clock: reduced ? Math.floor(clock / 60000) * 60000 : clock,
      weather: weather.kind,
      weatherVisible: layers.weather,
      buildingsVisible: layers.buildings,
      selected,
      select: selectItem,
      buildingsUrl: sample.buildingsUrl,
      buildingHash: sample.buildingHash,
    }),
    [
      trams,
      layers,
      clock,
      reduced,
      weather.kind,
      selected,
      selectItem,
      mapSites,
      sample,
    ],
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
    selectedSite = sites.find((s) => s.development_key === selected);
  return (
    <div className="explorer-shell">
      <header className="explorer-header">
        <a href={import.meta.env.BASE_URL} className="explorer-brand">
          UrbanPulse<span>Melbourne</span>
        </a>
        <span className="demo-pill">
          <i />
          Schedule sample · 8 Oct 2026
        </span>
      </header>
      <button className="sample-credit-button" onClick={() => setCredits(true)}>
        Sources & attribution
      </button>
      {credits && (
        <dialog
          open
          className="sample-credits"
          aria-label="Sources and attribution"
        >
          <button onClick={() => setCredits(false)}>Close sources</button>
          <h2>Sources and attribution</h2>
          <p>
            Schedule simulation, not live. Weather is synthetic. Original 3D
            models are illustrative.
          </p>
          {manifest.attribution.map((source) => (
            <section key={source.name}>
              <h3>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.name}
                </a>
              </h3>
              <p>{source.changes}</p>
              <a href={manifest.licence_url}>CC BY 4.0</a>
            </section>
          ))}
          <p>
            Dataset {manifest.version} · {manifest.date}. No endorsement by
            source publishers is implied.
          </p>
          <p>
            DAM status is not an actual worksite location. Footprints are
            historical surveys; the sample clock does not reconstruct planning
            or buildings for that time.
          </p>
        </dialog>
      )}
      <main className="explorer-stage">
        <div className="explorer-viewport">
          <CityMap
            boundary={boundary}
            localContext={localContext}
            vehicles={trams}
            selected={selectedTram?.id ?? null}
            onSelect={selectItem}
            showVehicles={layers.trams}
            showBoundary={false}
            showTracks={layers.tracks}
            warnings={emptyWarnings}
            showWarnings={false}
            developments={mapSites}
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
              <h1>CBD + Southbank</h1>
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
              Schedule simulation · not live
            </span>
            <span>
              <i className="amber" />
              DAM developments
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
              <span className="day-help">Sample · 8 October</span>
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
              <h2>CBD + Southbank</h2>
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
                  <p>A sample day cannot assess current conditions.</p>
                </div>
                <h4>Data coverage</h4>
                <ul className="coverage-list">
                  <li>
                    <span>Transport</span>
                    <strong>Schedule simulation</strong>
                  </li>
                  <li>
                    <span>Weather</span>
                    <strong>Synthetic</strong>
                  </li>
                  <li>
                    <span>Planning</span>
                    <strong>DAM snapshot</strong>
                  </li>
                </ul>
                <p>No live condition coverage or numerical health score.</p>
              </>
            )}
            {detail === 'trams' && (
              <>
                <p>
                  Schedule simulation, not live · {trams.length} scheduled trips
                  in view area
                </p>
                {trams.map((tram) => (
                  <button
                    className="detail-row"
                    key={tram.id}
                    aria-pressed={selected === tram.id}
                    onClick={() => select(tram.id)}
                  >
                    <span className="glance-dot teal" />
                    {tram.label}
                    <small>Route {tram.route_id}</small>
                  </button>
                ))}
              </>
            )}
            {detail === 'works' && (
              <>
                <p>
                  DAM status, not actual worksite location. Source:{' '}
                  {data.dam_date.slice(0, 10)}. Construction does not imply
                  disruption.
                </p>
                {sites.map((site) => (
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
                <p>Synthetic weather · authored sample day</p>
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
