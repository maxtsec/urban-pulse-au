import type { Moment } from './moments';

const THUMB = 16;

type Props = {
  clock: string;
  seconds: number;
  endSeconds: number;
  playing: boolean;
  canPlay: boolean;
  moments: Moment[];
  onPlay: () => void;
  onJump: (seconds: number) => void;
};

export function Timeline({
  clock,
  seconds,
  endSeconds,
  playing,
  canPlay,
  moments,
  onPlay,
  onJump,
}: Props) {
  const playingNow = playing && seconds < endSeconds;
  // Align markers with the range thumb centre, which is inset by half its width.
  const position = (value: number) => {
    const ratio = endSeconds ? value / endSeconds : 0;
    return `calc(${ratio * 100}% + ${(0.5 - ratio) * THUMB}px)`;
  };
  return (
    <section className="timeline" aria-label="Scenario playback">
      <div className="timeline-buttons">
        <button
          className="icon-button primary"
          aria-label={playingNow ? 'Pause' : 'Play scenario'}
          title={playingNow ? 'Pause' : 'Play scenario'}
          onClick={onPlay}
          disabled={!canPlay}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            {playingNow ? (
              <path d="M6 4h3v12H6zM11 4h3v12h-3z" />
            ) : (
              <path d="M6 4l10 6-10 6z" />
            )}
          </svg>
        </button>
        <button
          className="icon-button"
          aria-label="Reset"
          title="Reset to start"
          onClick={() => onJump(0)}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M5 8a6 6 0 1 1 0 4M5 3v5h5"
              fill="none"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
      <div className="timeline-clock">
        <strong data-testid="clock">{clock}</strong>
        <span>4 Oct 2026 · Melbourne</span>
      </div>
      <div className="timeline-track">
        <div
          className="moment-ticks"
          role="group"
          aria-label="Scenario moments"
        >
          {moments.map((moment) => (
            <button
              key={moment.seconds}
              className={`moment-tick ${moment.seconds === seconds ? 'current' : ''}`}
              aria-label={moment.label}
              style={{ left: position(moment.seconds) }}
              onClick={() => onJump(moment.seconds)}
            >
              <span className="moment-label" aria-hidden="true">
                {moment.label}
              </span>
            </button>
          ))}
        </div>
        <input
          aria-label="Scenario time"
          type="range"
          min="0"
          max={endSeconds}
          step="15"
          value={seconds}
          onChange={(event) => onJump(Number(event.target.value))}
        />
      </div>
      <output className="timeline-elapsed">
        {seconds}s<span> / {endSeconds}s</span>
      </output>
    </section>
  );
}
