import { DayPlayer } from './components/DayPlayer';
import { SourceCredits } from './components/SourceCredits';
import { InformationTabs } from './components/InformationTabs';
import type { InformationPage } from './components/InformationTabs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CityMap } from '../CityMap';
import type { Boundary } from '../CityMap';
import { makeSchedule, inArea } from './schedule';
import type { LoadedSample } from './sample';
import type { SampleData } from './schedule';
import type { SampleDay } from './day';
import { useReducedMotion } from '../useReducedMotion';
import { WINDOW_MS, weatherReadings, clockLabel, weatherAt } from './day';
import type { VisualScene } from './scene';
import './explorer.css';
import { useDayPlayback } from './useDayPlayback';
import { DayOverview } from './DayOverview';
import { HealthPanel } from './HealthPanel';
import {
  assessDemo,
  AREA_CENTRES,
  demoTramDelay,
  demoImpact,
} from './health-demo';
import type { DemoArea, DemoReason } from './health-demo';

const emptyWarnings: [] = [];
const icons = { sunny: '☀', cloudy: '☁', rainy: '☂' };

export function Explorer({ sample }: { sample: LoadedSample }) {
  const { data, manifest } = sample;
  const boundary: Boundary = useMemo(
    () => ({ revision: manifest.version, feature: data.boundary }),
    [data, manifest],
  );
  const sites = data.developments;
  const nonCompletedSites = useMemo(
    () => sites.filter((site) => site.status.toUpperCase() !== 'COMPLETED'),
    [sites],
  );
  const localContext = useMemo(
    () => ({
      tracks: data.display_tracks,
      roads: data.roads,
      water: data.water,
      focusMask: data.focus_mask,
    }),
    [data],
  );
  const [credits, setCredits] = useState(false);
  const [overview, setOverview] = useState(false);
  const reduced = useReducedMotion();
  const playback = useDayPlayback(reduced);
  const { day, selectDay } = playback;
  const [previousSchedule, setPreviousSchedule] = useState<
    SampleData['schedule'] | null
  >(null);
  const [previousLoading, setPreviousLoading] = useState(false);
  const [previousError, setPreviousError] = useState(false);
  const dayRequest = useRef(0);
  useEffect(
    () => () => {
      dayRequest.current += 1;
    },
    [],
  );
  async function requestDay(next: SampleDay) {
    const request = ++dayRequest.current;
    setPreviousError(false);
    setPreviousLoading(false);
    if (next === 'previous' && !previousSchedule) {
      setPreviousLoading(true);
      try {
        const loaded = await sample.loadPreviousSchedule();
        if (dayRequest.current !== request) return;
        setPreviousSchedule(loaded);
      } catch {
        if (dayRequest.current === request) setPreviousError(true);
        return;
      } finally {
        if (dayRequest.current === request) setPreviousLoading(false);
      }
    }
    selectDay(next);
    select(null);
    setLocatedReason(null);
  }
  function goLive() {
    dayRequest.current += 1;
    setPreviousLoading(false);
    setPreviousError(false);
    playback.goLive();
  }
  const schedule = useMemo(
    () =>
      makeSchedule({
        ...data,
        schedule: day === 'previous' ? previousSchedule! : data.schedule,
      }),
    [data, previousSchedule, day],
  );
  const { clock, edge, mode, chooseWindow } = playback;
  const cbdHealth = assessDemo('cbd', clock, day);
  const southbankHealth = assessDemo('southbank', clock, day);
  const assessments = { cbd: cbdHealth, southbank: southbankHealth };
  const healthAreas = useMemo(
    () => ({
      ...data.areas,
      features: data.areas.features.map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          status:
            feature.properties.area_id === 'cbd'
              ? cbdHealth.status
              : southbankHealth.status,
        },
      })),
    }),
    [data, cbdHealth.status, southbankHealth.status],
  );
  const [healthArea, setHealthArea] = useState<DemoArea>('southbank');
  const [locatedReason, setLocatedReason] = useState<DemoReason | null>(null);
  const [focusRequest, setFocusRequest] = useState<
    { center: [number, number]; zoom: number; id: number } | undefined
  >();
  const focusId = useRef(0);
  function focusHealthArea(area: DemoArea) {
    setHealthArea(area);
    setLocatedReason(null);
    setFocusRequest({
      center: AREA_CENTRES[area],
      zoom: 14.8,
      id: ++focusId.current,
    });
  }
  function locateReason(reason: DemoReason) {
    setLocatedReason(reason);
    setFocusRequest({
      center: reason.location,
      zoom: 16,
      id: ++focusId.current,
    });
  }
  const startDemo = useRef(
    new URLSearchParams(window.location.search).get('demo') === 'health',
  );
  useEffect(() => {
    if (startDemo.current) {
      startDemo.current = false;
      chooseWindow(8 * 3600000, 9.25 * 3600000);
    }
  }, [chooseWindow]);
  const currentReason =
    locatedReason &&
    assessments[locatedReason.area].reasons.find(
      (reason) => reason.id === locatedReason.id,
    );
  const [threeD, setThreeD] = useState(false);
  const [selected, select] = useState<string | null>(null);
  const [detail, setDetail] = useState<InformationPage>('health');
  const [showLayers, setShowLayers] = useState(false);
  const [layers, setLayers] = useState({
    buildings: true,
    trams: true,
    works: true,
    weather: true,
    tracks: true,
    streetNames: true,
    otherProjects: false,
  });
  const mapSites = useMemo(
    () =>
      nonCompletedSites.filter(
        (site) =>
          site.status.toUpperCase() === 'UNDER CONSTRUCTION' ||
          layers.otherProjects ||
          site.development_key === selected,
      ),
    [nonCompletedSites, layers.otherProjects, selected],
  );
  const { trams, tramDelays } = useMemo(() => {
    const delays: Record<string, DemoReason> = {};
    const items = schedule.at(clock).map((tram) => {
      const area = data.areas.features.find((feature) =>
        inArea([tram.longitude, tram.latitude], feature.geometry),
      )?.properties.area_id;
      const delay = area
        ? demoTramDelay(clock, tram.longitude, tram.latitude, area, day)
        : undefined;
      if (delay) delays[tram.id] = delay;
      return { ...tram, demoDelay: delay?.severity };
    });
    return { trams: items, tramDelays: delays };
  }, [clock, schedule, data, day]);
  const weather = weatherAt(clock, day);
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
        <label className="demo-pill sample-day-select">
          Sample date
          <select
            aria-label="Sample date"
            value={previousLoading ? 'previous' : day}
            onChange={(e) => {
              void requestDay(e.target.value as SampleDay);
            }}
          >
            <option value="today">8 Oct 2026 · Simulated today</option>
            <option value="previous">7 Oct 2026 · Full-day history</option>
          </select>
        </label>
      </header>
      <div className="demo-scenario-banner">
        <span>Demo scenario — scripted incidents, not real service status</span>
        <button
          className="sample-credit-button"
          onClick={() => setCredits(true)}
        >
          Sources &amp; attribution
        </button>
      </div>
      {previousLoading && (
        <div className="sample-load-notice" role="status">
          Loading and verifying 7 October… Current map stays on 8 October.
        </div>
      )}
      {previousError && (
        <div className="sample-load-notice" role="alert">
          7 October could not be verified. Current map is unchanged.{' '}
          <button
            onClick={() => {
              void requestDay('previous');
            }}
          >
            Retry previous day
          </button>
        </div>
      )}
      {credits && (
        <SourceCredits
          manifest={manifest}
          day={day}
          close={() => setCredits(false)}
        />
      )}
      {overview && (
        <DayOverview
          day={day}
          clock={clock}
          edge={edge}
          constructionCount={
            nonCompletedSites.filter(
              (s) =>
                s.applicable && s.status.toUpperCase() === 'UNDER CONSTRUCTION',
            ).length
          }
          damDate={data.dam_date}
          close={() => setOverview(false)}
          jump={(at, row) => {
            chooseWindow(Math.floor(at / WINDOW_MS) * WINDOW_MS, at);
            setLocatedReason(null);
            setDetail(row.kind);
            if (row.area) setHealthArea(row.area);
          }}
        />
      )}
      <main className="explorer-stage">
        <div className="explorer-viewport">
          <CityMap
            boundary={boundary}
            localContext={localContext}
            areaHealth={healthAreas}
            focusRequest={focusRequest}
            showStreetNames={layers.streetNames}
            tramDelays={tramDelays}
            declutterLabels
            vehicles={trams}
            selected={selectedTram?.id ?? null}
            onSelect={selectItem}
            showVehicles={layers.trams}
            showBoundary={true}
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
                  {key === 'streetNames'
                    ? 'Main street names'
                    : key === 'otherProjects'
                      ? 'Other development projects'
                      : key === 'works'
                        ? 'Development markers'
                        : key}
                </label>
              ))}
              <p>Models and weather effects appear in 3D.</p>
              <p>
                2D projects: yellow helmet = DAM under construction; blue plan =
                other development status.
              </p>
            </section>
          )}
          {currentReason && (
            <aside
              className="health-map-callout glass"
              aria-label="Located demo impact"
            >
              <button
                aria-label="Close impact"
                onClick={() => setLocatedReason(null)}
              >
                ×
              </button>
              <strong>{currentReason.title} · Demo</strong>
              <p>{currentReason.detail}</p>
            </aside>
          )}
          <div className="explorer-legend glass">
            <span>
              <i className="teal" />
              Schedule simulation · not live
            </span>
            <span>
              <i className="amber" />
              DAM construction status
            </span>
            <span>
              <i className="amber" />
              Demo delay
            </span>
            <span>
              <i className="red" />
              Severe demo delay
            </span>
          </div>
          <DayPlayer
            playback={playback}
            reduced={reduced}
            goLive={goLive}
            openOverview={() => setOverview(true)}
          />
        </div>
        <aside className="explorer-details glass" aria-label="Area information">
          <div className="detail-heading">
            <div>
              <span className="panel-eyebrow">AREA INFORMATION</span>
              <h2>CBD + Southbank</h2>
            </div>
            <span className="panel-clock">{clockLabel(clock)}</span>
          </div>
          <InformationTabs detail={detail} setDetail={setDetail} />
          <section
            className="information-content"
            id="information-content"
            role="tabpanel"
            aria-labelledby={`tab-${detail}`}
          >
            {detail === 'health' && (
              <HealthPanel
                routes={{
                  cbd: [
                    ...new Set(
                      trams
                        .filter((t) => tramDelays[t.id]?.area === 'cbd')
                        .map((t) => t.route_id ?? 'Unknown'),
                    ),
                  ].sort(),
                  southbank: [
                    ...new Set(
                      trams
                        .filter((t) => tramDelays[t.id]?.area === 'southbank')
                        .map((t) => t.route_id ?? 'Unknown'),
                    ),
                  ].sort(),
                }}
                impact={demoImpact(
                  trams,
                  healthArea,
                  data.areas.features.find(
                    (f) => f.properties.area_id === healthArea,
                  )!.geometry,
                  clock,
                  day,
                )}
                day={day}
                assessments={assessments}
                selected={healthArea}
                clock={clock}
                edge={edge}
                sites={sites}
                damDate={data.dam_date}
                select={focusHealthArea}
                locate={locateReason}
                jump={(at) => {
                  setLocatedReason(null);
                  setHealthArea(
                    assessDemo('southbank', at, day).status === 'clear'
                      ? 'cbd'
                      : 'southbank',
                  );
                  chooseWindow(Math.floor(at / WINDOW_MS) * WINDOW_MS, at);
                }}
              />
            )}
            {detail === 'trams' && (
              <>
                <p>
                  Schedule simulation, not live · {trams.length} scheduled trips
                  in view area
                </p>
                {selectedTram && tramDelays[selectedTram.id] && (
                  <div
                    className={`tram-delay-detail ${selectedTram.demoDelay}`}
                  >
                    <strong>
                      Demo delay · {tramDelays[selectedTram.id].title}
                    </strong>
                    <p>{tramDelays[selectedTram.id].detail}</p>
                    <small>
                      Authored zone highlight; timetable movement is unchanged.
                    </small>
                  </div>
                )}
                {trams.map((tram) => (
                  <button
                    className="detail-row"
                    key={tram.id}
                    aria-pressed={selected === tram.id}
                    onClick={() => select(tram.id)}
                  >
                    <span
                      className={`glance-dot ${tram.demoDelay ?? 'teal'}`}
                    />
                    {tram.label}
                    <small>
                      {tram.demoDelay
                        ? `${tram.demoDelay === 'severe' ? 'Severe demo delay' : 'Demo delay'} · `
                        : ''}
                      Route {tram.route_id}
                    </small>
                  </button>
                ))}
              </>
            )}
            {detail === 'works' && (
              <>
                <p>
                  DAM status, not actual worksite location. Source:{' '}
                  {data.dam_date.slice(0, 10)}. Construction does not imply
                  disruption. Yellow helmets indicate UNDER CONSTRUCTION; blue
                  plans indicate other non-completed statuses. The map starts
                  with construction only; select a project to reveal it or
                  enable other projects in Layers.
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
                {weatherReadings(day)
                  .filter(
                    (reading) => reading.at * 3600000 <= Math.min(clock, edge),
                  )
                  .map((reading) => (
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
