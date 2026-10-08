import { useEffect, useRef, useState } from 'react';
import './pipeline-demo.css';

type Area = 'cbd' | 'southbank';
type Reading = {
  vehicles: number | null;
  freshness: number | null;
  captures: number;
};
type Interval = {
  start: string;
  end: string;
  cbd: Reading;
  southbank: Reading;
};

// Authored presentation fixtures, not schedule-derived metrics or collector results.
const intervals: Interval[] = [
  {
    start: '08:00',
    end: '08:15',
    cbd: { vehicles: 38, freshness: 94, captures: 15 },
    southbank: { vehicles: 17, freshness: 91, captures: 15 },
  },
  {
    start: '08:15',
    end: '08:30',
    cbd: { vehicles: 44, freshness: 99, captures: 15 },
    southbank: { vehicles: 21, freshness: 95, captures: 15 },
  },
  {
    start: '08:30',
    end: '08:45',
    cbd: { vehicles: 49, freshness: 103, captures: 15 },
    southbank: { vehicles: 25, freshness: 98, captures: 15 },
  },
  {
    start: '08:45',
    end: '09:00',
    cbd: { vehicles: 41, freshness: 148, captures: 10 },
    southbank: { vehicles: 19, freshness: 141, captures: 10 },
  },
  {
    start: '09:00',
    end: '09:15',
    cbd: { vehicles: null, freshness: null, captures: 0 },
    southbank: { vehicles: null, freshness: null, captures: 0 },
  },
  {
    start: '09:15',
    end: '09:30',
    cbd: { vehicles: 46, freshness: 109, captures: 15 },
    southbank: { vehicles: 23, freshness: 104, captures: 15 },
  },
  {
    start: '09:30',
    end: '09:45',
    cbd: { vehicles: 39, freshness: 96, captures: 15 },
    southbank: { vehicles: 20, freshness: 93, captures: 15 },
  },
  {
    start: '09:45',
    end: '10:00',
    cbd: { vehicles: 35, freshness: 92, captures: 15 },
    southbank: { vehicles: 16, freshness: 90, captures: 15 },
  },
];
const names = { cbd: 'CBD', southbank: 'Southbank' };
const examples = [
  {
    title: 'Rerun a partition',
    before: '120 rows already published',
    action: 'Replay the same 120 record keys',
    after: '120 rows · 0 extra rows',
    meaning:
      'Stable keys let a rerun replace the same logical rows instead of appending duplicates.',
  },
  {
    title: 'Recover an upload',
    before: 'Object stored; response lost',
    action: 'Retry the same object and verify its checksum',
    after: 'One object · confirmation recorded',
    meaning:
      'A retry confirms the existing object before advancing progress. A mismatch stops for review.',
  },
  {
    title: 'Keep a collection gap',
    before: 'No captures from 09:00–09:15',
    action: 'Publish the interval with missing coverage',
    after: 'Vehicle count N/A · gap retained',
    meaning:
      'Missing observations do not become zero vehicles. A later backfill can replace this incomplete interval.',
  },
];
const steps = [
  ['Collect', 'Local Tram raw'],
  ['Normalize', 'Parquet → GCS'],
  ['Model', 'BigQuery + dbt'],
  ['Serve', 'PostGIS → API'],
  ['Explore', 'Map + trends'],
];

export function PipelineDemo({ close }: { close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<'data' | 'how'>('data');
  const [area, setArea] = useState<Area>('cbd');
  const [index, setIndex] = useState(2);
  const [example, setExample] = useState(0);
  const interval = intervals[index];
  const reading = interval[area];
  const state =
    reading.captures === 0
      ? 'Missing'
      : reading.captures < 15
        ? 'Partial'
        : 'Complete';
  const current = examples[example];
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="pipeline-dialog"
      aria-labelledby="pipeline-title"
      onClose={close}
    >
      <header className="pipeline-heading">
        <div>
          <span className="pipeline-badge">MOCK · NOT CONNECTED</span>
          <h2 id="pipeline-title">From observations to insight</h2>
          <p>Explore a trend. Check the evidence behind it.</p>
        </div>
        <button
          autoFocus
          className="pipeline-close"
          aria-label="Close data and pipeline"
          onClick={() => dialog.current?.close()}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="m6 6 12 12M18 6 6 18"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>
      <div
        className="pipeline-tabs"
        role="tablist"
        aria-label="Data and pipeline pages"
      >
        {(['data', 'how'] as const).map((id) => (
          <button
            key={id}
            id={`pipeline-tab-${id}`}
            role="tab"
            aria-selected={tab === id}
            aria-controls="pipeline-content"
            tabIndex={tab === id ? 0 : -1}
            onClick={() => setTab(id)}
            onKeyDown={(e) => {
              if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key))
                return;
              e.preventDefault();
              const next =
                e.key === 'Home'
                  ? 'data'
                  : e.key === 'End'
                    ? 'how'
                    : tab === 'data'
                      ? 'how'
                      : 'data';
              setTab(next);
              document.getElementById(`pipeline-tab-${next}`)?.focus();
            }}
          >
            {id === 'data' ? 'Trend preview' : 'How it works'}
          </button>
        ))}
      </div>
      <section
        id="pipeline-content"
        role="tabpanel"
        aria-labelledby={`pipeline-tab-${tab}`}
      >
        {tab === 'data' ? (
          <>
            <div className="pipeline-section-heading">
              <div>
                <h3>A morning, in 15-minute intervals</h3>
                <p>7 Oct 2026 · 08:00–10:00 · Melbourne time</p>
              </div>
              <span>Authored mock values</span>
            </div>
            <div className="pipeline-chart-key">
              <span>
                <i className="cbd" />
                CBD
              </span>
              <span>
                <i className="southbank" />
                Southbank
              </span>
              <span>
                <i className="gap" />
                Missing captures
              </span>
            </div>
            <div
              className="pipeline-chart"
              role="group"
              aria-label="Compare mock vehicle observations by interval"
            >
              {intervals.map((slot, i) => (
                <button
                  key={slot.start}
                  aria-pressed={index === i}
                  aria-label={`${slot.start} to ${slot.end}: CBD ${slot.cbd.vehicles ?? 'N/A'}, Southbank ${slot.southbank.vehicles ?? 'N/A'}; ${slot.cbd.captures}/15 captures`}
                  onClick={() => setIndex(i)}
                >
                  <span className="pipeline-bars" aria-hidden="true">
                    {(['cbd', 'southbank'] as const).map((key) => (
                      <span
                        key={key}
                        className={`pipeline-bar ${key} ${slot[key].vehicles === null ? 'gap' : ''} ${slot[key].captures > 0 && slot[key].captures < 15 ? 'partial' : ''}`}
                        style={{
                          height:
                            slot[key].vehicles === null
                              ? '100%'
                              : `${(slot[key].vehicles / 55) * 100}%`,
                        }}
                      >
                        {slot[key].vehicles ?? '—'}
                      </span>
                    ))}
                  </span>
                  <span className="pipeline-tick">{slot.start}</span>
                </button>
              ))}
            </div>
            <p className="pipeline-chart-note">
              Different vehicles observed in each interval. Hatched bars have
              partial coverage; gaps stay empty.
            </p>
            <div className="pipeline-controls">
              <div role="group" aria-label="Choose metric area">
                {(['cbd', 'southbank'] as const).map((id) => (
                  <button
                    key={id}
                    aria-pressed={area === id}
                    onClick={() => setArea(id)}
                  >
                    {names[id]}
                  </button>
                ))}
              </div>
              <strong>
                {interval.start}–{interval.end}{' '}
                <span className={`pipeline-coverage ${state.toLowerCase()}`}>
                  {state}
                </span>
              </strong>
            </div>
            <div className="pipeline-stats" aria-live="polite">
              <article>
                <span>Observed vehicles</span>
                <strong data-testid="mock-vehicles">
                  {reading.vehicles ?? 'N/A'}
                </strong>
                <small>
                  {reading.captures === 0
                    ? 'No observations available'
                    : `Distinct vehicle IDs · ${names[area]}`}
                </small>
              </article>
              <article>
                <span>Median position age</span>
                <strong data-testid="mock-freshness">
                  {reading.freshness === null
                    ? 'N/A'
                    : `${reading.freshness} s`}
                </strong>
                <small>At collection, not viewing time</small>
              </article>
              <article>
                <span>Successful captures</span>
                <strong data-testid="mock-captures">
                  {reading.captures}
                  <em>/15</em>
                </strong>
                <small>{15 - reading.captures} missing · positions feed</small>
              </article>
            </div>
            <p className={`pipeline-reading ${state.toLowerCase()}`}>
              {state === 'Missing'
                ? 'A blank interval means missing data, not an empty city.'
                : state === 'Partial'
                  ? 'Fewer captures can lower the observed count. Compare this interval with care.'
                  : 'Compare areas and time periods. Vehicle counts alone do not measure congestion or service quality.'}
            </p>
            <details className="pipeline-method">
              <summary>What will these metrics mean?</summary>
              <ul>
                <li>
                  Vehicle count: distinct vehicle IDs with a valid position
                  inside the area during [start, end). A vehicle can appear in
                  both areas during one interval.
                </li>
                <li>
                  Position age: median of received_at − observed_at across
                  deduplicated valid observations. Exclude missing or future
                  observation times; keep them as quality issues.
                </li>
                <li>
                  Capture coverage: successful positions captures / scheduled
                  attempts. This mock assumes one attempt per minute, shared by
                  both areas; it is not route coverage.
                </li>
              </ul>
              <p>
                Illustrative definitions for this UI; production SQL and metric
                rules still require review. Numbers are authored separately from
                the schedule map and do not change area health.
              </p>
            </details>
          </>
        ) : (
          <>
            <div className="pipeline-section-heading">
              <div>
                <h3>The intended data journey</h3>
                <p>A traceable path from a capture to an area summary.</p>
              </div>
            </div>
            <ol className="pipeline-flow">
              {steps.map(([title, subtitle]) => (
                <li key={title}>
                  <strong>{title}</strong>
                  <span>{subtitle}</span>
                </li>
              ))}
            </ol>
            <p className="pipeline-chart-note">
              Target flow. This static page runs no cloud jobs and reads no
              warehouse or database.
            </p>
            <h3 className="pipeline-example-title">
              Three behaviours worth demonstrating
            </h3>
            <div
              className="pipeline-examples"
              role="group"
              aria-label="Choose engineering example"
            >
              {examples.map((item, i) => (
                <button
                  key={item.title}
                  aria-pressed={example === i}
                  onClick={() => setExample(i)}
                >
                  {item.title}
                </button>
              ))}
            </div>
            <section
              className="pipeline-example"
              aria-label="Illustrative engineering outcome"
              aria-live="polite"
            >
              <span className="pipeline-badge">
                ILLUSTRATIVE · NOT A TEST RUN
              </span>
              <dl>
                <div>
                  <dt>Before</dt>
                  <dd>{current.before}</dd>
                </div>
                <div>
                  <dt>Action</dt>
                  <dd>{current.action}</dd>
                </div>
                <div>
                  <dt>Expected result</dt>
                  <dd>{current.after}</dd>
                </div>
              </dl>
              <p>{current.meaning}</p>
            </section>
            <div className="pipeline-evidence">
              <h3>Inspect the actual project</h3>
              <p>
                These links document existing contracts and recovery work; they
                do not prove the mock pipeline has run.
              </p>
              <a
                href="https://github.com/maxtsec/urban-pulse-au/blob/main/docs/architecture/normalized-tram-contract.md"
                target="_blank"
                rel="noreferrer"
              >
                Tram data contract ↗
              </a>
              <a
                href="https://github.com/maxtsec/urban-pulse-au/blob/main/docs/evidence/event-01-worker-recovery.md"
                target="_blank"
                rel="noreferrer"
              >
                Worker recovery evidence ↗
              </a>
              <a
                href="https://github.com/maxtsec/urban-pulse-au/blob/main/docs/runbooks/event-recovery.md"
                target="_blank"
                rel="noreferrer"
              >
                Retry & recovery runbook ↗
              </a>
            </div>
          </>
        )}
      </section>
      <footer>
        Frontend prototype · fixed mock partition · real pipeline results will
        replace these values.
      </footer>
    </dialog>
  );
}
