import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DAY_MS,
  INITIAL_MS,
  LIVE_START_MS,
  WINDOW_MS,
  availableWindow,
  clampClock,
  historyClock,
  liveEdgeAt,
} from './day';

/** One monotonic live edge, shared by playback, seeking and future-data gating. */
export function useDayPlayback(reduced: boolean) {
  const [clock, setClock] = useState(LIVE_START_MS);
  const [edge, setEdge] = useState(LIVE_START_MS);
  const [mode, setMode] = useState<'live' | 'history'>('live');
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(30);
  const [selectedWindow, setSelectedWindow] = useState(INITIAL_MS);
  const anchor = useRef<number | null>(null);
  const clockRef = useRef(clock);
  const tick = useCallback((value: number) => {
    clockRef.current = value;
    setClock(value);
  }, []);
  const nowEdge = useCallback(
    () =>
      liveEdgeAt(
        anchor.current === null ? 0 : performance.now() - anchor.current,
      ),
    [],
  );
  useEffect(() => {
    anchor.current ??= performance.now();
    const timer = window.setInterval(() => setEdge(nowEdge()), 1000);
    return () => window.clearInterval(timer);
  }, [nowEdge]);
  useEffect(() => {
    if (mode !== 'live' && (!playing || reduced)) return;
    const started = performance.now(),
      from = clockRef.current;
    let frame = 0,
      timer = 0,
      last = 0;
    const step = (now: number) => {
      const latest = nowEdge();
      if (now - last >= (reduced ? 1000 : 33)) {
        const end = availableWindow(selectedWindow, latest).end;
        const next =
          mode === 'live'
            ? latest
            : Math.min(end, clampClock(from + (now - started) * speed));
        tick(next);
        last = now;
        if (mode === 'history' && next >= end) {
          setPlaying(false);
          if (end === latest) setMode('live');
          return;
        }
        if (next >= DAY_MS) {
          setPlaying(false);
          return;
        }
      }
      if (reduced)
        timer = window.setTimeout(() => step(performance.now()), 1000);
      else frame = requestAnimationFrame(step);
    };
    step(started);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [mode, playing, reduced, speed, selectedWindow, nowEdge, tick]);
  function seek(value: number) {
    setPlaying(false);
    setMode('history');
    tick(historyClock(value, nowEdge()));
  }
  function goLive() {
    setPlaying(false);
    setMode('live');
    tick(nowEdge());
  }
  function chooseWindow(start: number) {
    const latest = nowEdge();
    if (start >= latest) return;
    setSelectedWindow(start);
    seek(start);
  }
  function togglePlay() {
    if (mode === 'live') {
      setMode('history');
      setSelectedWindow(
        Math.floor(Math.max(0, clockRef.current - WINDOW_MS) / 1000) * 1000,
      );
      setPlaying(false);
      return;
    }
    if (clockRef.current >= availableWindow(selectedWindow, nowEdge()).end) {
      goLive();
      return;
    }
    setPlaying(!playing);
  }
  const visibleWindow =
    mode === 'live'
      ? {
          start: Math.floor(Math.max(0, clock - WINDOW_MS) / 1000) * 1000,
          end: Math.floor(clock / 1000) * 1000,
        }
      : availableWindow(selectedWindow, Math.max(edge, clock));
  return {
    clock,
    edge: Math.max(edge, mode === 'live' ? clock : edge),
    mode,
    playing,
    speed,
    setSpeed,
    seek,
    goLive,
    chooseWindow,
    togglePlay,
    window: visibleWindow,
  };
}
