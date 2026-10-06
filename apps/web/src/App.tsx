import { useCallback, useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AREA_ID, displayTime, readJson } from './city';
import type { Development, Snapshot, Warning } from './city';
import { CityMap } from './CityMap';
import type { Boundary, Insets } from './CityMap';
import { AreaOverview } from './AreaOverview';
import { DetailsPanel } from './DetailsPanel';
import type { Tab } from './DetailsPanel';
import { LayersMenu } from './LayersMenu';
import type { Layers } from './LayersMenu';
import { PlanningPanel } from './PlanningPanel';
import { SelectionCard } from './SelectionCard';
import { ScenarioPicker, initialScenario, scenarios } from './ScenarioPicker';
import { Timeline } from './Timeline';
import { TramList } from './TramList';
import { WeatherPanel } from './WeatherPanel';
import { WeatherSummary } from './WeatherSummary';
import { conditionLabel, missingCoverage } from './conditions';
import { scenarioMoments } from './moments';
import { useReducedMotion } from './useReducedMotion';

const EMPTY_WARNINGS: Warning[] = [];
const EMPTY_DEVELOPMENTS: Development[] = [];
const WIDE = 900;
const PLAY_STEP_SECONDS = 15;
const PLAY_STEP_MS = 2000;
const SCRUB_SETTLE_MS = 250;
// Shorter than a playback step so each tram settles on its observation before the next one.
const GLIDE_MS = 1500;

function mapInsets(): Insets {
  // Keep the initial area clear of the chips, timeline and (on wide screens) the details panel.
  return window.innerWidth >= WIDE
    ? { top: 84, right: 420, bottom: 120, left: 40 }
    : { top: 116, right: 20, bottom: 124, left: 20 };
}

export function App() {
  const reducedMotion = useReducedMotion();
  const [seconds, setSeconds] = useState(0);
  const [scrubSeconds, setScrubSeconds] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [scenario, setScenario] = useState(initialScenario);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedDevelopment, setSelectedDevelopment] = useState<string | null>(
    null,
  );
  const [threeDimensional, setThreeDimensional] = useState(false);
  const [layers, setLayers] = useState<Layers>({
    buildings: true,
    vehicles: true,
    boundary: true,
    tracks: true,
    planning: true,
    warnings: true,
  });
  const [tab, setTab] = useState<Tab>('overview');
  const [panelOpen, setPanelOpen] = useState(true);
  const [insets] = useState(mapInsets);
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
      setScrubSeconds(null);
      setPlaying(false);
      setSelected(null);
      setSelectedDevelopment(null);
    }
    window.addEventListener('popstate', restoreScenario);
    return () => window.removeEventListener('popstate', restoreScenario);
  }, []);

  // The thumb follows input immediately; queries wait until scrubbing settles.
  useEffect(() => {
    if (scrubSeconds === null) return;
    const timer = window.setTimeout(() => {
      setSeconds(scrubSeconds);
      setScrubSeconds(null);
    }, SCRUB_SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [scrubSeconds]);

  const selectVehicle = useCallback((id: string) => {
    setSelected(id);
    setSelectedDevelopment(null);
  }, []);
  const selectDevelopment = useCallback((id: string) => {
    setSelectedDevelopment(id);
    setSelected(null);
  }, []);

  // Playback waits for each snapshot, then advances one step after a fixed delay.
  const advancing =
    playing && Boolean(snapshot) && !result.isFetching && seconds < endSeconds;
  const nextSeconds = Math.min(seconds + PLAY_STEP_SECONDS, endSeconds);
  useEffect(() => {
    if (!advancing) return;
    const timer = window.setTimeout(
      () => setSeconds(nextSeconds),
      PLAY_STEP_MS,
    );
    return () => window.clearTimeout(timer);
  }, [advancing, nextSeconds]);

  function changeScenario(value: string) {
    if (value !== scenario) {
      const url = new URL(window.location.href);
      url.searchParams.set('scenario', value);
      window.history.pushState(null, '', url);
    }
    setScrubSeconds(null);
    setScenario(value);
    setPlaying(false);
    setSelected(null);
    setSelectedDevelopment(null);
  }

  function scrub(value: number) {
    setPlaying(false);
    setScrubSeconds(Math.max(0, Math.min(value, endSeconds)));
  }

  function jump(value: number) {
    setScrubSeconds(null);
    setPlaying(false);
    setSeconds(Math.max(0, Math.min(value, endSeconds)));
  }

  function play() {
    if (scrubSeconds !== null) {
      setSeconds(scrubSeconds >= endSeconds ? 0 : scrubSeconds);
      setScrubSeconds(null);
      setPlaying(true);
      return;
    }
    if (seconds >= endSeconds) {
      setSeconds(0);
      setPlaying(true);
    } else {
      setPlaying((value) => !value);
    }
  }

  function showTab(next: Tab) {
    setTab(next);
    setPanelOpen(true);
  }

  const visible = snapshot && !result.isError ? snapshot : undefined;
  const records = visible?.planning.records;
  const warnings = visible?.weather?.warnings ?? EMPTY_WARNINGS;
  const activeWarningAreas = warnings.filter(
    (warning) => warning.lifecycle === 'active' && warning.geometry,
  ).length;
  const tabs: { id: Tab; label: string; count?: number }[] = visible
    ? [
        { id: 'overview', label: 'Overview' },
        { id: 'trams', label: 'Trams', count: visible.vehicles.length },
        ...(records
          ? [
              {
                id: 'developments' as const,
                label: 'Developments',
                count: records.length,
              },
            ]
          : []),
        ...(visible.weather
          ? [
              {
                id: 'warnings' as const,
                label: 'Warnings',
                count: warnings.length,
              },
            ]
          : []),
      ]
    : [];
  // A tab the current scenario does not provide falls back to the overview.
  const currentTab = tabs.some((item) => item.id === tab) ? tab : 'overview';
  const condition = visible?.assessment.condition ?? 'unknown';
  const allDevelopments = [
    ...(records ?? []),
    ...(visible?.planning.unlocated_records ?? []),
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="UrbanPulse home">
          UrbanPulse
        </a>
        <span className="city-name">Melbourne, Victoria</span>
        <span className="fixture-badge">SYNTHETIC DEMO · NO LIVE DATA</span>
      </header>
      <main
        className={`stage ${panelOpen && visible ? 'panel-open' : ''}`}
        aria-busy={result.isPlaceholderData}
      >
        <div className="map-area">
          {geometry.data && visible && (
            <CityMap
              boundary={geometry.data}
              vehicles={visible.vehicles}
              selected={selected}
              onSelect={selectVehicle}
              showVehicles={layers.vehicles}
              showBoundary={layers.boundary}
              showTracks={layers.tracks}
              warnings={warnings}
              showWarnings={layers.warnings}
              developments={records ?? EMPTY_DEVELOPMENTS}
              showPlanning={layers.planning}
              selectedDevelopment={selectedDevelopment}
              onSelectDevelopment={selectDevelopment}
              insets={insets}
              glideMs={
                playing && !reducedMotion && !threeDimensional ? GLIDE_MS : 0
              }
              threeDimensional={threeDimensional}
              showBuildings={layers.buildings}
            />
          )}
          {visible && geometry.isPending && (
            <div className="map-placeholder" role="status">
              Loading area boundary…
            </div>
          )}
          {visible && geometry.isError && (
            <div className="map-placeholder" role="alert">
              Boundary unavailable. Observations remain in the details panel.
              <button onClick={() => geometry.refetch()}>Retry boundary</button>
            </div>
          )}

          <div className="map-top">
            <div className="area-title">
              <h1>Southbank</h1>
              <span>City of Melbourne · CLUE area</span>
            </div>
            <ScenarioPicker value={scenario} onChange={changeScenario} />
            {visible && (
              <>
                <button
                  className={`chip condition-chip ${condition}`}
                  data-testid="condition"
                  onClick={() => showTab('overview')}
                  title="Open area conditions"
                >
                  <span
                    className={`condition-dot ${condition}`}
                    aria-hidden="true"
                  />
                  <span className="chip-caption">Conditions</span>
                  <strong>{conditionLabel(condition)}</strong>
                  <span className="condition-why">
                    {visible.assessment.reasons.length
                      ? `${visible.assessment.reasons.length} active ${visible.assessment.reasons.length === 1 ? 'reason' : 'reasons'}`
                      : condition === 'unknown'
                        ? missingCoverage(visible)
                        : 'Required inputs complete'}
                  </span>
                </button>
                <WeatherSummary weather={visible.weather} />
                <span className="chip map-counts">
                  {layers.vehicles && (
                    <span data-testid="tram-map-count">
                      {visible.vehicles.filter((v) => v.visible_on_map).length}{' '}
                      trams on map
                    </span>
                  )}
                  {layers.planning && records && records.length > 0 && (
                    <span data-testid="planning-map-count">
                      {records.length} developments
                    </span>
                  )}
                  {layers.warnings && warnings.length > 0 && (
                    <span data-testid="warning-map-count">
                      {activeWarningAreas} active warning{' '}
                      {activeWarningAreas === 1 ? 'area' : 'areas'}
                    </span>
                  )}
                </span>
              </>
            )}
            <span className="map-top-spacer" />
            {visible && (
              <button
                className="chip"
                aria-label="3D view"
                aria-pressed={threeDimensional}
                onClick={() => setThreeDimensional(!threeDimensional)}
              >
                3D
              </button>
            )}
            {visible && (
              <LayersMenu
                layers={layers}
                threeDimensional={threeDimensional}
                onChange={setLayers}
                hasPlanning={Boolean(records)}
                hasWarnings={Boolean(visible.weather)}
              />
            )}
            {visible && !panelOpen && (
              <button
                className="chip show-panel"
                onClick={() => setPanelOpen(true)}
              >
                Show details
              </button>
            )}
          </div>

          {snapshot && snapshot.scenario !== scenario && (
            <div className="map-notice" role="status">
              Loading scenario… Still showing{' '}
              {scenarios.find((item) => item.id === snapshot.scenario)?.label}.
            </div>
          )}
          {result.isPending && (
            <div className="map-notice" role="status">
              Loading city observations…
            </div>
          )}
          {result.isError && (
            <div className="map-alert" role="alert">
              <strong>City snapshot unavailable</strong>
              <p>
                Start the local API and PostGIS, then try again. No current
                conditions can be shown.
              </p>
              <button onClick={() => result.refetch()}>Try again</button>
            </div>
          )}

          {visible && (
            <SelectionCard
              tramId={selected}
              tram={visible.vehicles.find((vehicle) => vehicle.id === selected)}
              developmentId={selectedDevelopment}
              development={allDevelopments.find(
                (record) => record.development_key === selectedDevelopment,
              )}
              onClose={() => {
                setSelected(null);
                setSelectedDevelopment(null);
              }}
            />
          )}

          <Timeline
            clock={snapshot ? displayTime(snapshot.clock.at) : '—'}
            seconds={scrubSeconds ?? seconds}
            endSeconds={endSeconds}
            playing={playing}
            advancing={advancing && !reducedMotion}
            nextSeconds={nextSeconds}
            stepMs={PLAY_STEP_MS}
            canPlay={!(result.isError || result.isPlaceholderData || !snapshot)}
            moments={visible ? scenarioMoments(visible) : []}
            onPlay={play}
            onJump={jump}
            onScrub={scrub}
          />
        </div>

        {visible && panelOpen && (
          <DetailsPanel
            tabs={tabs}
            active={currentTab}
            onSelect={setTab}
            onHide={() => setPanelOpen(false)}
          >
            {currentTab === 'overview' && (
              <AreaOverview
                snapshot={visible}
                onShowDevelopments={() => setTab('developments')}
              />
            )}
            {currentTab === 'trams' && (
              <TramList
                snapshot={visible}
                selected={selected}
                onSelect={selectVehicle}
              />
            )}
            {currentTab === 'developments' && (
              <PlanningPanel
                planning={visible.planning}
                selected={selectedDevelopment}
                onSelect={selectDevelopment}
              />
            )}
            {currentTab === 'warnings' && visible.weather && (
              <WeatherPanel weather={visible.weather} />
            )}
          </DetailsPanel>
        )}
      </main>
    </div>
  );
}
