import { useSyncExternalStore } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

function subscribe(changed: () => void) {
  const media = window.matchMedia(QUERY);
  media.addEventListener('change', changed);
  return () => media.removeEventListener('change', changed);
}

export function useReducedMotion() {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => true,
  );
}
