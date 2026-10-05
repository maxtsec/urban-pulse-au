import type { Polygon, MultiPolygon } from 'geojson';

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
      input_id: string;
      effective_until: string | null;
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
  weather: WeatherSnapshot | null;
  planning: PlanningProfile;
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

export type Warning = {
  id: string;
  level: string;
  headline: string;
  description: string;
  issued_at: string;
  updated_at: string;
  effective_from: string;
  effective_until: string;
  lifecycle: 'active' | 'scheduled' | 'cancelled' | 'expired';
  applicable: boolean | null;
  recognized: boolean;
  geometry: Polygon | MultiPolygon | null;
  source_url: string;
};

export type WeatherSnapshot = {
  reading: {
    kind: 'modelled';
    model: string;
    valid_at: string;
    temperature_c: number;
    precipitation_mm: number;
    wind_kmh: number;
    source_url: string;
  } | null;
  warnings: Warning[];
  coverage: string;
  last_feed_update_received_at: string | null;
  attribution: { owner: string; notice_url: string };
  projection: Snapshot['projection'];
};

export function displayDateTime(value: string | null) {
  if (!value) return 'No successful receipt';
  return new Intl.DateTimeFormat('en-AU', {
    timeZone: 'Australia/Melbourne',
    dateStyle: 'medium',
    timeStyle: 'long',
  }).format(new Date(value));
}

export type Development = {
  development_key: string;
  name: string;
  status: string;
  clue_small_area: string | null;
  position: { longitude: number; latitude: number } | null;
  year_completed: number | null;
  applicable: boolean | null;
};

export type PlanningProfile = {
  state: string;
  capture_state?: string;
  as_of: string | null;
  description: string;
  snapshot_id?: string | null;
  last_successful_received_at?: string | null;
  records?: Development[];
  unlocated_records?: Development[];
  removed_records?: (Development & { last_seen_as_of: string | null })[];
  projection?: Snapshot['projection'];
  incomplete_captures?: number;
  attribution?: {
    owner: string;
    source_url: string;
    licence_url: string;
    modifications: string;
  };
};

export function displaySourceDate(value: string | null) {
  return value
    ? new Intl.DateTimeFormat('en-AU', {
        timeZone: 'Australia/Melbourne',
        dateStyle: 'medium',
      }).format(new Date(value))
    : 'Source date unknown';
}
