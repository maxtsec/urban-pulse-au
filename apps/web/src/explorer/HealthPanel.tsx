import {
  AREA_NAMES,
  healthMoments,
  STATUS_PRESENTATION,
  demoChanges,
} from './health-demo';
import type {
  DemoArea,
  DemoAssessment,
  DemoReason,
  DemoImpact,
} from './health-demo';
import { clockLabel, SAMPLE_DATES } from './day';
import type { SampleDay } from './day';
import type { Development } from '../city';
type Props = {
  day: SampleDay;
  impact: DemoImpact;
  assessments: Record<DemoArea, DemoAssessment>;
  selected: DemoArea;
  clock: number;
  routes: Record<DemoArea, string[]>;
  edge: number;
  sites: Development[];
  damDate: string;
  select: (area: DemoArea) => void;
  locate: (reason: DemoReason) => void;
  jump: (at: number) => void;
};
export function HealthPanel({
  day,
  impact,
  assessments,
  selected,
  clock,
  routes,
  edge,
  sites,
  damDate,
  select,
  locate,
  jump,
}: Props) {
  const assessment = assessments[selected],
    presentation = STATUS_PRESENTATION[assessment.status],
    changes = demoChanges(selected, clock, day);
  const projects = sites.filter(
    (s) =>
      s.applicable &&
      s.clue_small_area ===
        (selected === 'cbd' ? 'Melbourne (CBD)' : 'Southbank') &&
      s.status.toUpperCase() !== 'COMPLETED',
  ).length;
  return (
    <div className="health-demo compact-health">
      <p className="health-demo-label">
        DEMO CONDITIONS <span>{SAMPLE_DATES[day]} · Not live</span>
      </p>
      <div
        className="health-area-picker"
        role="group"
        aria-label="Choose health area"
      >
        {(['cbd', 'southbank'] as const).map((area) => (
          <button
            key={area}
            aria-pressed={selected === area}
            onClick={() => select(area)}
          >
            <span
              className={`condition-dot ${assessments[area].status}`}
              aria-hidden="true"
            />
            <strong>{AREA_NAMES[area]}</strong>
            <small>{STATUS_PRESENTATION[assessments[area].status].label}</small>
          </button>
        ))}
      </div>
      <section
        className={`condition-card ${assessment.status}`}
        aria-label={`${AREA_NAMES[selected]} demo condition`}
      >
        <span className="condition-symbol" aria-hidden="true">
          {presentation.symbol}
        </span>
        <div>
          <span>
            {AREA_NAMES[selected]} · {clockLabel(clock)}
          </span>
          <h3>{presentation.label}</h3>
          <strong className="scripted-status-notice">
            Demo scenario — scripted incidents, not real service status
          </strong>
        </div>
      </section>
      <section
        className="health-impact-stat"
        aria-label="Demo affected-trip share"
      >
        <div>
          <strong>
            {impact.percent === null ? 'N/A' : `${impact.percent}%`}
          </strong>
          <span>Demo affected trips</span>
        </div>
        <p>
          {impact.reason === 'missing'
            ? 'Transport data missing'
            : impact.reason === 'empty'
              ? 'No scheduled trips in area'
              : `${impact.affected} / ${impact.total} scheduled trips at ${clockLabel(clock)}`}
        </p>
        <small>Sample impact · not measured delay</small>
      </section>
      <div className="condition-reasons">
        {assessment.reasons.map((reason) => (
          <button
            className={`condition-reason ${reason.severity}`}
            key={reason.id}
            onClick={() => locate(reason)}
          >
            <span>{reason.domain === 'weather' ? '☂' : '↔'}</span>
            <div>
              <strong>{reason.title}</strong>
              <small>Demo · since {clockLabel(reason.start)}</small>
            </div>
            <span aria-hidden="true">↗</span>
          </button>
        ))}
      </div>
      {routes[selected].length > 0 && (
        <p className="health-route-summary">
          Demo routes {routes[selected].join(' · ')}
        </p>
      )}
      <p className="condition-coverage">
        <strong>Demo inputs {2 - assessment.missing.length}/2</strong>
        <span>
          {assessment.missing.length
            ? 'Transport unavailable · weather available'
            : 'Transport + weather available'}
        </span>
      </p>
      <section className="health-story">
        <h4>Explore the story</h4>
        <div>
          {healthMoments(day).map((moment) => (
            <button
              key={moment.at}
              disabled={moment.at > edge}
              onClick={() => jump(moment.at)}
            >
              <span>{moment.label}</span>
              <small>{clockLabel(moment.at)}</small>
            </button>
          ))}
        </div>
      </section>
      <details className="health-method">
        <summary>Method & area profile</summary>
        <p>
          Demo affected-trip share = scheduled trips inside this area and an
          active demo transport-impact zone / all scheduled trips currently
          inside this area. Trip IDs are counted once. N/A means missing
          transport coverage or no trips; percentage is rounded to a whole
          number.
        </p>
        <p>
          This is a single-time sample, not actual punctuality, road congestion,
          or a period average. Weather impacts do not enter the percentage.
          Confirmed impacts remain visible when another input is missing.
        </p>
        <p>
          Map movement still follows the published schedule. Green means
          complete demo inputs without known impacts; amber is local impact, red
          major interruption, grey incomplete inputs.
        </p>
        <div className="health-profile">
          <strong>Area profile</strong>
          <span>{projects} non-completed DAM projects</span>
          <small>
            Snapshot {damDate.slice(0, 10)} · context only, does not lower
            health
          </small>
        </div>
        <p>
          Last scripted change {clockLabel(changes.previous)}
          {changes.next !== null ? ` · Next ${clockLabel(changes.next)}` : ''}
        </p>
      </details>
    </div>
  );
}
