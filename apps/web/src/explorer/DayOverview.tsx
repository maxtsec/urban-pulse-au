import type { SampleDay } from './day';
import { useEffect, useMemo, useRef } from 'react';
import { DAY_MS, clockLabel, SAMPLE_DATES } from './day';
import { dayRows } from './day-overview';
import type { DayRow } from './day-overview';
type Props = {
  day: SampleDay;
  clock: number;
  edge: number;
  constructionCount: number;
  damDate: string;
  close: () => void;
  jump: (at: number, row: DayRow) => void;
};
export function DayOverview({
  day,
  clock,
  edge,
  constructionCount,
  damDate,
  close,
  jump,
}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const rows = useMemo(
    () => dayRows(edge, constructionCount, damDate, day),
    [edge, constructionCount, damDate, day],
  );
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="day-overview glass"
      aria-labelledby="day-overview-title"
      onClose={close}
    >
      <header>
        <div>
          <span>{SAMPLE_DATES[day]} · SAMPLE DAY</span>
          <h2 id="day-overview-title">Day overview</h2>
          <p>Spot a change, then select a time to explore the map.</p>
        </div>
        <button
          autoFocus
          aria-label="Close day overview"
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
      <div className="overview-key">
        <span>
          <i className="clear" />
          No demo delay
        </span>
        <span>
          <i className="affected" />
          Local delay
        </span>
        <span>
          <i className="severe" />
          Severe delay
        </span>
        <span>
          <i className="unknown" />
          Missing data
        </span>
        <span>Tram conditions: Demo · Weather: Synthetic</span>
      </div>
      <div
        className="overview-scroll"
        tabIndex={0}
        aria-label="Scrollable 24-hour timetable"
      >
        <div className="overview-table">
          <div className="overview-axis">
            <span>Melbourne time</span>
            <div>
              {Array.from({ length: 13 }, (_, i) => (
                <time key={i} style={{ left: `${(i / 12) * 100}%` }}>
                  {clockLabel(i * 7200000)}
                </time>
              ))}
            </div>
          </div>
          {rows.map((row) => (
            <div className="overview-row" key={row.id}>
              <strong>{row.label}</strong>
              <div
                className="overview-track"
                role="group"
                aria-label={`${row.label} timeline`}
              >
                {row.segments.map((segment) => (
                  <button
                    key={segment.start}
                    className={`overview-segment ${segment.tone}`}
                    style={{
                      left: `${(segment.start / DAY_MS) * 100}%`,
                      width: `${((segment.end - segment.start) / DAY_MS) * 100}%`,
                    }}
                    title={`${clockLabel(segment.start)}–${clockLabel(segment.end)} · ${segment.detail}`}
                    aria-label={`${row.label}: ${segment.label}, ${clockLabel(segment.start)} to ${clockLabel(segment.end)}. ${segment.detail}`}
                    onClick={() => {
                      jump(segment.start, row);
                      close();
                    }}
                  >
                    <span aria-hidden="true">
                      {
                        (
                          {
                            clear: '',
                            affected: '!',
                            severe: '!',
                            unknown: '?',
                            sunny: '☀',
                            cloudy: '☁',
                            rainy: '☂',
                            snapshot: '',
                          } as Record<string, string>
                        )[segment.tone]
                      }
                    </span>
                  </button>
                ))}
                {edge < DAY_MS && (
                  <div
                    className="overview-future"
                    style={{ left: `${(edge / DAY_MS) * 100}%`, right: 0 }}
                    aria-label="Future times unavailable"
                  >
                    After simulated Live
                  </div>
                )}
                <div
                  className="overview-cursor"
                  style={{ left: `${(clock / DAY_MS) * 100}%` }}
                  aria-hidden="true"
                />
              </div>
            </div>
          ))}
          <div className="overview-now">
            Viewing {clockLabel(clock)} ·{' '}
            {day === 'previous'
              ? 'Full 24-hour history'
              : `Simulated Live ${clockLabel(edge)}`}
          </div>
        </div>
      </div>
      <section className="overview-moments" aria-label="Timetable details">
        <strong>Time & conditions</strong>
        <p className="overview-caption">
          Exact intervals below — colours above show their duration.
        </p>
        <div className="overview-detail-grid">
          {rows.map((row) => (
            <section key={row.id}>
              <h3>{row.label}</h3>
              {row.segments.map((segment) => (
                <button
                  key={`${row.id}-${segment.start}`}
                  className={`overview-detail ${segment.tone}`}
                  onClick={() => {
                    jump(segment.start, row);
                    close();
                  }}
                >
                  <time>
                    {clockLabel(segment.start)}–{clockLabel(segment.end)}
                  </time>
                  <span>{segment.label}</span>
                </button>
              ))}
            </section>
          ))}
        </div>
      </section>
      <footer>
        <p>
          <strong>Development is a snapshot, not a work schedule.</strong>{' '}
          {constructionCount} mapped projects have DAM status UNDER
          CONSTRUCTION. Source {damDate.slice(0, 10)}; no start/stop hours are
          known.
        </p>
        <p>
          {day === 'previous'
            ? 'The complete previous sample day is selectable.'
            : 'Only elapsed demo time is selectable; future cells stay hidden until simulated Live reaches them.'}{' '}
          Select a time range below to explore its conditions.
        </p>
      </footer>
    </dialog>
  );
}
