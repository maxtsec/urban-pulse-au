import {
  AREA_NAMES,
  HEALTH_MOMENTS,
  STATUS_PRESENTATION,
  demoChanges,
} from './health-demo';
import type { DemoArea, DemoAssessment, DemoReason } from './health-demo';
import { clockLabel } from './day';
import type { Development } from '../city';
type Props = {
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
  assessments,
  selected,
  clock,
  edge,
  sites,
  damDate,
  select,
  locate,
  jump,
  routes,
}: Props) {
  const assessment = assessments[selected],
    presentation = STATUS_PRESENTATION[assessment.status];
  const projects = sites.filter(
    (s) =>
      s.applicable &&
      s.clue_small_area ===
        (selected === 'cbd' ? 'Melbourne (CBD)' : 'Southbank'),
  );
  const changes = demoChanges(selected, clock);
  const nonCompleted = projects.filter(
    (s) => s.status.toUpperCase() !== 'COMPLETED',
  ).length;
  return (
    <div className="health-demo">
      <p className="health-demo-label">
        DEMO CONDITIONS <span>Not live measurements</span>
      </p>
      <div
        className="health-area-picker"
        role="group"
        aria-label="Choose health area"
      >
        {(['cbd', 'southbank'] as const).map((area) => {
          const style = STATUS_PRESENTATION[assessments[area].status];
          return (
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
              <small>{style.label}</small>
            </button>
          );
        })}
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
        </div>
        <p>
          {assessment.status === 'clear'
            ? 'Both demo inputs are available, with no active demo impacts.'
            : assessment.status === 'unknown'
              ? 'A missing source cannot be treated as a healthy area.'
              : `${assessment.reasons.length} active demo ${assessment.reasons.length === 1 ? 'impact' : 'impacts'}. Select a reason to locate it.`}
        </p>
      </section>
      <section className="health-journey">
        <h4>What affects your visit?</h4>
        <p>
          {assessment.status === 'clear'
            ? 'No active impacts in this demo. Explore nearby routes and development projects.'
            : assessment.status === 'unknown'
              ? 'Transport information is missing. Check service updates before relying on this view.'
              : assessment.reasons.some((r) => r.domain === 'transport')
                ? 'Check the highlighted tram routes before travelling through this area.'
                : 'A demo weather warning is active. Check the warning details before heading out.'}
        </p>
        {routes[selected].length > 0 && (
          <small>Demo-highlighted routes: {routes[selected].join(', ')}</small>
        )}
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
              <small>
                Demo · {reason.domain} · since {clockLabel(reason.start)}
              </small>
            </div>
            <span aria-hidden="true">↗</span>
          </button>
        ))}
      </div>
      <p className="condition-coverage">
        <strong>Demo inputs {2 - assessment.missing.length}/2</strong>
        <span>
          {assessment.missing.length
            ? 'Transport unavailable · weather available'
            : 'Transport + weather available'}
        </span>
      </p>
      <div className="health-changes">
        <span>
          Last demo change <strong>{clockLabel(changes.previous)}</strong>
        </span>
        {changes.next !== null && (
          <button
            disabled={changes.next > edge}
            onClick={() => jump(changes.next!)}
          >
            Next scripted change · {clockLabel(changes.next)} →
          </button>
        )}
      </div>
      <details className="health-method">
        <summary>What does this mean?</summary>
        <p>
          Colours describe authored impacts, not a calculated congestion or
          health score. Confirmed impacts stay visible even if another source is
          missing. Map trams are schedule simulations; the coloured delay
          overlays do not alter their movement.
        </p>
        <p>
          Green: no known demo impact. Amber: local impact. Red: major
          interruption. Grey: insufficient inputs. Numeric health scoring
          remains undefined.
        </p>
      </details>
      <section className="health-story">
        <h4>Explore the story</h4>
        <div>
          {HEALTH_MOMENTS.map((moment) => (
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
      <div className="health-profile">
        <strong>Area profile</strong>
        <span>{nonCompleted} non-completed DAM projects</span>
        <small>
          Snapshot {damDate.slice(0, 10)} · context only, does not lower health
        </small>
      </div>
    </div>
  );
}
