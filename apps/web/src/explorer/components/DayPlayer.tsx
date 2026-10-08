import { WINDOW_MS, clockLabel, weatherAt } from '../day';
import type { useDayPlayback } from '../useDayPlayback';

type Props = {
  playback: ReturnType<typeof useDayPlayback>;
  reduced: boolean;
  goLive: () => void;
  openOverview: () => void;
};

export function DayPlayer({ playback, reduced, goLive, openOverview }: Props) {
  const {
    clock,
    edge,
    mode,
    playing,
    speed,
    setSpeed,
    seek,
    chooseWindow,
    togglePlay,
    day,
  } = playback;
  const { start: windowStart, end: windowEnd } = playback.window;
  return (
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
            : day === 'previous'
              ? 'Full-day history · 7 October'
              : `${clockLabel(Math.max(0, edge - clock), true)} behind live`}
        </span>
        <button
          className="day-help overview-open"
          onClick={openOverview}
          aria-haspopup="dialog"
        >
          ▦ Day overview
        </button>
      </div>
      <div className="playback-line">
        <button
          className="play-toggle"
          aria-label={mode === 'live' || playing ? 'Pause demo' : 'Play demo'}
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
                {clockLabel(windowStart + (i * (windowEnd - windowStart)) / 4)}
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
        {Array.from({ length: 12 }, (_, i) => i * WINDOW_MS).map((start) => (
          <button
            key={start}
            aria-label={`${clockLabel(start)} to ${clockLabel(start + WINDOW_MS)}`}
            disabled={start >= edge}
            aria-pressed={clock >= start && clock < start + WINDOW_MS}
            onClick={() => chooseWindow(start)}
          >
            <span>{clockLabel(start)}</span>
            <i
              className={start < edge ? weatherAt(start, day).kind : 'future'}
            />
          </button>
        ))}
      </div>
      <div className="player-footnote">
        <span>
          {reduced
            ? 'Reduced motion · use the time slider'
            : mode === 'live'
              ? 'Live follows a simulated clock. No live feeds connected.'
              : day === 'previous'
                ? 'Full 24-hour sample · all times available'
                : 'Today’s history · future times are unavailable'}
        </span>
        <span>Sunny · Cloudy · Rainy</span>
      </div>
    </section>
  );
}
