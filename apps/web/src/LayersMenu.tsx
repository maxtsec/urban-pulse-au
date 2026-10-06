export type Layers = {
  buildings: boolean;
  vehicles: boolean;
  boundary: boolean;
  tracks: boolean;
  planning: boolean;
  warnings: boolean;
};

type Props = {
  layers: Layers;
  onChange: (layers: Layers) => void;
  hasPlanning: boolean;
  hasWarnings: boolean;
  threeDimensional: boolean;
};

export function LayersMenu({
  layers,
  onChange,
  hasPlanning,
  hasWarnings,
  threeDimensional,
}: Props) {
  const toggle = (key: keyof Layers, label: string, legend: string) => (
    <label className="layer-option">
      <input
        type="checkbox"
        checked={layers[key]}
        onChange={(event) =>
          onChange({ ...layers, [key]: event.target.checked })
        }
      />
      <span>{label}</span>
      <i className={`legend-swatch ${legend}`} aria-hidden="true" />
    </label>
  );
  return (
    <details className="layers-menu">
      <summary className="chip">
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path
            d="M10 3l7 4-7 4-7-4zM3 11l7 4 7-4"
            fill="none"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
        Layers
      </summary>
      <div className="layers-popover">
        <fieldset>
          <legend>Show on map</legend>
          {threeDimensional &&
            toggle('buildings', 'Buildings (historical)', 'building')}
          {toggle('vehicles', 'Tram positions', 'tram')}
          {toggle('boundary', 'Area boundary', 'boundary')}
          {toggle('tracks', 'Tracks (illustrative)', 'track')}
          {hasPlanning && toggle('planning', 'Development sites', 'site')}
          {hasWarnings && toggle('warnings', 'Warning areas', 'warning')}
        </fieldset>
        <div className="legend" aria-label="Tram freshness legend" role="group">
          <span>
            <i className="legend-dot" aria-hidden="true" /> Current
          </span>
          <span>
            <i className="legend-dot stale" aria-hidden="true" /> Stale
          </span>
          <span>
            <i className="legend-dot unknown" aria-hidden="true" /> Time unknown
          </span>
        </div>
        {layers.tracks && (
          <p className="layers-note" data-testid="tracks-note">
            Illustrative tracks. Tram positions are synthetic fixture
            observations.
          </p>
        )}
        {threeDimensional && (
          <p className="layers-note">
            Observed � historical building massing, captured 2018�2023. Drag
            with the right mouse button to rotate; use the compass to reset
            north. Tram markers retain the existing fixture positions.
          </p>
        )}
        <details className="layers-note">
          <summary>Map display classes</summary>
          <dl>
            <dt>Observed</dt>
            <dd>
              A received record or historical captured geometry; not necessarily
              current.
            </dd>
            <dt>Interpolated</dt>
            <dd>Between received positions on a verified path (MAP-02).</dd>
            <dt>Modelled</dt>
            <dd>Weather model output, not a station observation.</dd>
            <dt>Simulated</dt>
            <dd>
              Illustrative activity with no measured traffic meaning (MAP-05).
            </dd>
            <dt>Decorative</dt>
            <dd>Presentation effects with no data meaning.</dd>
          </dl>
        </details>
        <p className="layers-note" data-testid="motion-note">
          During playback, trams glide between observed positions. The movement
          is animated, not observed; details show the observation.
        </p>
      </div>
    </details>
  );
}
