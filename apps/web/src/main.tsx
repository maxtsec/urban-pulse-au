import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query';
import './style.css';

type Fixture = {
  mode: string;
  description: string;
  observations: {
    route_id: string;
    stop_id: string;
    delay_seconds: number | null;
  }[];
};

function App() {
  const result = useQuery<Fixture>({
    queryKey: ['fixture'],
    queryFn: async () => {
      const response = await fetch('/api/v1/fixture');
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      return response.json();
    },
    retry: false,
  });
  return (
    <main>
      <p className="eyebrow">MELBOURNE · ENVIRONMENT BASELINE</p>
      <h1>UrbanPulse AU</h1>
      <p>React + TypeScript + FastAPI development workspace</p>
      <p className="badge">SYNTHETIC FIXTURE — NO LIVE DATA</p>
      {result.isPending && <p>Connecting to the local API…</p>}
      {result.isError && (
        <p role="alert">{result.error.message}. Start the API on port 8000.</p>
      )}
      {result.data && (
        <>
          <p>{result.data.description}</p>
          <table>
            <thead>
              <tr>
                <th>Route</th>
                <th>Stop</th>
                <th>Reported delay (seconds)</th>
              </tr>
            </thead>
            <tbody>
              {result.data.observations.map((row) => (
                <tr key={`${row.route_id}:${row.stop_id}`}>
                  <td>{row.route_id}</td>
                  <td>{row.stop_id}</td>
                  <td>{row.delay_seconds ?? 'Unknown'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            The planned city view combines transport, weather and
            infrastructure. This table verifies the local environment with a
            transport fixture.
          </p>
        </>
      )}
      <a href="http://127.0.0.1:8000/docs">Open local API documentation</a>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
