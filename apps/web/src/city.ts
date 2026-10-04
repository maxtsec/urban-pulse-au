export const AREA_ID = 'au-vic-melbourne-clue-southbank';

export type Vehicle = {
  id: string;
  label: string;
  route_id: string | null;
  longitude: number;
  latitude: number;
  observed_at: string | null;
  freshness: 'current' | 'stale' | 'expired' | 'unknown';
  visible_on_map: boolean;
  event_id: string;
  revision: number;
  capture_ids: string[];
};

export type Snapshot = {
  mode: 'fixture';
  area: { id: string; name: string; boundary_revision: string };
  geometry_url: string;
  policy_version: string;
  scenario: string;
  clock: { at: string; seconds: number; end_seconds: number };
  assessment: {
    condition: 'normal' | 'degraded' | 'unknown';
    reasons: {
      id: string;
      reason: string;
      effective_from: string;
      resolved_at: string | null;
    }[];
    coverage: { input_id: string; state: string }[];
    incomplete_inputs: string[];
    evaluated_at: string;
  };
  vehicles: Vehicle[];
  positions_total: number;
  positions_limit: number;
  positions_truncated: boolean;
  projection: {
    apply: number;
    duplicate: number;
    superseded: number;
    conflict: number;
    rejected: number;
  };
  planning: { state: string; as_of: string | null; description: string };
  evidence_url: string;
};

export async function readJson<T>(
  url: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export function displayTime(value: string | null) {
  if (!value) return 'Observation time unknown';
  return new Intl.DateTimeFormat('en-AU', {
    timeZone: 'Australia/Melbourne',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value));
}
