import { useEffect, useMemo, useRef } from 'react';
import { DAY_MS, clockLabel } from './day';
import { dayRows } from './day-overview';
import type { DayRow } from './day-overview';
type Props = {
  clock: number;
  edge: number;
  constructionCount: number;
  damDate: string;
  close: () => void;
  jump: (at: number, row: DayRow) => void;
};
export function DayOverview({
  clock,
  edge,
  constructionCount,
  damDate,
  close,
  jump,
}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const rows = useMemo(
    () => dayRows(edge, constructionCount, damDate),
    [edge, constructionCount, damDate],
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
          <span>8 OCTOBER 2026 · SAMPLE DAY</span>
          <h2 id="day-overview-title">Day overview</h2>
          <p>Spot a change, then select a time to explore the map.</p>
        </div>
        <button
          autoFocus
          aria-label="Close day overview"
          onClick={() => dialog.current?.close()}
        >
          ×
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
                    <span>
                      {segment.end - segment.start > 3600000
                        ? segment.label
                        : segment.tone === 'severe'
                          ? '!!'
                          : segment.tone === 'affected'
                            ? '!'
                            : segment.tone === 'unknown'
                              ? '?'
                              : segment.tone === 'rainy'
                                ? '☂'
                                : segment.tone === 'cloudy'
                                  ? '☁'
                                  : segment.tone === 'sunny'
                                    ? '☀'
                                    : '✓'}
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
            Viewing {clockLabel(clock)} · Simulated Live {clockLabel(edge)}
          </div>
        </div>
      </div>
      <section className="overview-moments" aria-label="Changes today">
        <strong>Changes today</strong>
        <div>
          {rows.flatMap((row) =>
            row.segments
              .filter(
                (segment) =>
                  segment.start > 0 &&
                  (row.kind === 'weather' ||
                    ['affected', 'severe', 'unknown'].includes(segment.tone)),
              )
              .map((segment) => (
                <button
                  key={`${row.id}-${segment.start}`}
                  onClick={() => {
                    jump(segment.start, row);
                    close();
                  }}
                >
                  <time>{clockLabel(segment.start)}</time>
                  {row.label} · {segment.label}
                </button>
              )),
          )}
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
          Only elapsed demo time is selectable. Future cells stay hidden until
          simulated Live reaches them. Hover or focus a block for its time
          range; select it to jump.
        </p>
      </footer>
    </dialog>
  );
}
