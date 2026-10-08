import { lazy, Suspense, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const Explorer = lazy(() =>
  import('./explorer/Explorer').then((module) => ({
    default: module.Explorer,
  })),
);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<p role="status">Loading city…</p>}>
      <Explorer />
    </Suspense>
  </StrictMode>,
);
