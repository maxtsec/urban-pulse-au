import { lazy, Suspense, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import './style.css';

const Explorer = lazy(() =>
  import('./explorer/Explorer').then((module) => ({
    default: module.Explorer,
  })),
);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <Suspense fallback={<p role="status">Loading city…</p>}>
        {new URLSearchParams(window.location.search).get('experience') ===
        'day' ? (
          <Explorer />
        ) : (
          <App />
        )}
      </Suspense>
    </QueryClientProvider>
  </StrictMode>,
);
