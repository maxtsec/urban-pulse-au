import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CityMap } from '../CityMap';
import type { Boundary } from '../CityMap';
import boundaryFeature from '../assets/southbank-boundary.json';
import { useReducedMotion } from '../useReducedMotion';
import {
  DAY_MS,
  WINDOW_MS,
  INITIAL_MS,
  SITES,
  WEATHER,
  clampClock,
  clockLabel,
  tramsAt,
  weatherAt,
  windowFor,
} from './day';
import type { VisualScene } from './scene';
import './explorer.css';

const boundary: Boundary = {
  revision: 'synthetic-preview-boundary',
  feature: boundaryFeature as Boundary['feature'],
};
const emptyWarnings: [] = [];
const icons = { sunny: '☀', cloudy: '☁', rainy: '☂' };

export function Explorer() {
  const reduced = useReducedMotion();
  const [clock, setClock] = useState(INITIAL_MS);
  const [windowStart, setWindowStart] = useState(INITIAL_MS);
  const [mode, setMode] = useState<'live' | 'history'>('history');
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(30);
  const [threeD, setThreeD] = useState(false);
  const [selected, select] = useState<string | null>(null);
  const [detail, setDetail] = useState<'trams' | 'works' | 'weather' | null>(
    null,
  );
  const [showLayers, setShowLayers] = useState(false);
  const [layers, setLayers] = useState({
    buildings: true,
    trams: true,
    works: true,
    weather: true,
    tracks: true,
  });
  const liveAnchor = useRef<number | null>(null);
  const clockRef = useRef(clock);
  const windowEnd = windowStart + WINDOW_MS;
  const tick = useCallback((next: number) => {
    clockRef.current = next;
    setClock(next);
  }, []);
  useEffect(() => {
    if ((!playing && mode !== 'live') || reduced) return;
    let frame = 0,
      last = 0;
    const start = performance.now(),
      from = clockRef.current;
    const step = (now: number) => {
      // Render at most 30 times/second; sample time comes from the anchor, never repeated additions.
      if (now - last >= 33) {
        const next =
          mode === 'live'
            ? clampClock(INITIAL_MS + now - (liveAnchor.current ?? now))
            : Math.min(windowEnd, clampClock(from + (now - start) * speed));
        tick(next);
        last = now;
        if (mode === 'live') setWindowStart(windowFor(next));
        if (next >= (mode === 'live' ? DAY_MS : windowEnd)) {
          setPlaying(false);
          return;
        }
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing, mode, speed, windowEnd, reduced, tick]);
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
  const insets = useMemo(
    () =>
      window.innerWidth >= 900
        ? { top: 135, right: 55, bottom: 195, left: 55 }
        : { top: 170, right: 24, bottom: 240, left: 24 },
    [],
  );
  function seek(ms: number) {
    setPlaying(false);
    setMode('history');
    tick(clampClock(ms));
  }
  function chooseWindow(start: number) {
    setWindowStart(start);
    seek(start);
  }
  function changeMode(next: 'live' | 'history') {
    setPlaying(false);
    setMode(next);
    if (next === 'live') {
      liveAnchor.current ??= performance.now();
      const edge = clampClock(
        INITIAL_MS + performance.now() - liveAnchor.current,
      );
      tick(edge);
      setWindowStart(windowFor(edge));
    }
  }
  const selectedTram = trams.find((t) => t.id === selected),
    selectedSite = SITES.find((s) => s.development_key === selected);
  return (
    <div className="explorer-shell">
      <header className="explorer-header">
        <a href="/?experience=day" className="explorer-brand">
          UrbanPulse<span>Melbourne</span>
        </a>
        <span className="demo-pill">
          <i />
          Synthetic · 8 Oct 2026
        </span>
        <a className="scenario-link" href="/?scenario=city">
          Scenarios ↗
        </a>
      </header>
      <main className="explorer-stage">
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
        <section className="city-glance glass" aria-label="City summary">
          <button
            aria-expanded={detail === 'weather'}
            onClick={() => setDetail(detail === 'weather' ? null : 'weather')}
          >
            <span className={`glance-icon ${weather.kind}`}>
              {icons[weather.kind]}
            </span>
            <span>
              <strong>
                {weather.temperature}°{' '}
                <span className="weather-name">{weather.kind}</span>
              </strong>
              <small>Synthetic weather</small>
            </span>
          </button>
          <button
            aria-expanded={detail === 'trams'}
            onClick={() => setDetail(detail === 'trams' ? null : 'trams')}
          >
            <span className="glance-dot teal" />
            <span>
              <strong>6 trams</strong>
              <small>Simulated movement</small>
            </span>
          </button>
          <button
            aria-expanded={detail === 'works'}
            onClick={() => setDetail(detail === 'works' ? null : 'works')}
          >
            <span className="glance-dot amber" />
            <span>
              <strong>2 active works</strong>
              <small>1 planned project</small>
            </span>
          </button>
        </section>
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
        {detail && (
          <aside
            className="explorer-details glass"
            aria-label={`${detail} details`}
          >
            <div className="detail-heading">
              <h2>
                {detail === 'works'
                  ? 'Development'
                  : detail === 'trams'
                    ? 'Around the tracks'
                    : 'Weather today'}
              </h2>
              <button
                aria-label="Close details"
                onClick={() => setDetail(null)}
              >
                ×
              </button>
            </div>
            {detail === 'trams' && (
              <>
                <p>
                  Simulated trams on illustrative tracks. Positions use two
                  minute-spaced samples with a 60-second display delay.
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
                <p>
                  Authored weather for this demo, not a forecast or warning.
                </p>
                {WEATHER.map((reading) => (
                  <button
                    key={reading.at}
                    className="detail-row"
                    onClick={() => {
                      chooseWindow(windowFor(reading.at * 3600000));
                      seek(reading.at * 3600000);
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
          </aside>
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
            <div className="mode-toggle">
              <button
                aria-pressed={mode === 'live'}
                onClick={() => changeMode('live')}
              >
                Live
              </button>
              <button
                aria-pressed={mode === 'history'}
                onClick={() => changeMode('history')}
              >
                History
              </button>
            </div>
            <span className="player-context">
              {mode === 'live'
                ? 'Simulated live · 1×'
                : '8 October · Melbourne'}
            </span>
            <button className="day-help" onClick={() => setDetail('weather')}>
              24-hour day ↗
            </button>
          </div>
          <div className="playback-line">
            <button
              className="play-toggle"
              aria-label={playing ? 'Pause demo' : 'Play demo'}
              disabled={mode === 'live' || reduced}
              onClick={() => {
                if (clock >= windowEnd) tick(windowStart);
                setPlaying(!playing);
              }}
            >
              {playing ? 'Ⅱ' : '▶'}
            </button>
            <output className="day-clock" data-testid="day-clock">
              {clockLabel(clock, true)}
            </output>
            <div className="day-range">
              <input
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
                    {clockLabel(windowStart + (i * WINDOW_MS) / 4)}
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
                  aria-pressed={start === windowStart}
                  onClick={() => chooseWindow(start)}
                >
                  <span>{clockLabel(start)}</span>
                  <i className={weatherAt(start).kind} />
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
                  : 'Choose a 2-hour window · 24 hours available'}
            </span>
            <span>Sunny · Cloudy · Rainy</span>
          </div>
        </section>
      </main>
    </div>
  );
}
