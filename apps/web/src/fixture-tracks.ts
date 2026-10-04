import type { FeatureCollection, LineString } from 'geojson';

// Illustrative fixture geometry only; never used for spatial membership or routing.
export const fixtureTracks: FeatureCollection<LineString> = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { kind: 'illustrative', name: 'Fixture track A' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [144.9515, -37.8245],
          [144.955, -37.824],
          [144.958, -37.824],
          [144.9617, -37.82529],
          [144.9622, -37.8249],
          [144.964, -37.8254],
          [144.967, -37.8275],
          [144.968, -37.8292],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { kind: 'illustrative', name: 'Fixture track B' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [144.9622, -37.8249],
          [144.9628, -37.823],
          [144.967, -37.8215],
          [144.971, -37.819],
        ],
      },
    },
  ],
};
