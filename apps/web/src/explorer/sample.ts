import cityUrl from '../assets/sample/city.json?url';
import previousScheduleUrl from '../assets/sample/previous-schedule.json?url';
import manifestUrl from '../assets/sample/manifest.json?url';
import buildingsUrl from '../assets/sample/buildings.geojson?url';
import type { SampleData } from './schedule';
export type SampleManifest = {
  version: string;
  date: string;
  files: Record<string, { bytes: number; sha256: string }>;
  attribution: { name: string; url: string; changes: string }[];
  licence_url: string;
};
export async function verifiedBytes(
  url: string,
  expected: { bytes: number; sha256: string },
) {
  const response = await fetch(url);
  if (!response.ok) throw new Error('Sample data unavailable');
  const bytes = await response.arrayBuffer();
  const hash = Array.from(
    new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    (b) => b.toString(16).padStart(2, '0'),
  ).join('');
  if (bytes.byteLength !== expected.bytes || hash !== expected.sha256)
    throw new Error('Sample data version mismatch');
  return bytes;
}
export async function loadSample() {
  const response = await fetch(manifestUrl);
  if (!response.ok) throw new Error('Sample manifest unavailable');
  const manifest = (await response.json()) as SampleManifest;
  if (manifest.version !== 'schedule-sample-v1')
    throw new Error('Unsupported sample version');
  const data = JSON.parse(
    new TextDecoder().decode(
      await verifiedBytes(cityUrl, manifest.files['city.json']),
    ),
  ) as SampleData;
  return {
    data,
    manifest,
    previousSchedule: JSON.parse(
      new TextDecoder().decode(
        await verifiedBytes(
          previousScheduleUrl,
          manifest.files['previous-schedule.json'],
        ),
      ),
    ) as SampleData['schedule'],
    buildingsUrl,
    buildingHash: manifest.files['buildings.geojson'].sha256,
  };
}
export type LoadedSample = Awaited<ReturnType<typeof loadSample>>;
