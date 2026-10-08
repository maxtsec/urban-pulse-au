import { useEffect, useState } from 'react';
import { Explorer } from './Explorer';
import { loadSample } from './sample';
import type { LoadedSample } from './sample';
export function SampleExplorer() {
  const [sample, setSample] = useState<LoadedSample | null>(null),
    [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    loadSample()
      .then((s) => {
        if (active) setSample(s);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, []);
  if (error)
    return (
      <main>
        <h1>City sample unavailable</h1>
        <p>The sample could not be verified. Reload to try again.</p>
      </main>
    );
  if (!sample) return <p role="status">Loading Melbourne sample…</p>;
  return <Explorer sample={sample} />;
}
