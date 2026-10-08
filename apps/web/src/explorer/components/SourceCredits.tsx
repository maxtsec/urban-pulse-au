import type { LoadedSample } from '../sample';
import { SAMPLE_DATES } from '../day';
import type { SampleDay } from '../day';

type Props = {
  manifest: LoadedSample['manifest'];
  day: SampleDay;
  close: () => void;
};

export function SourceCredits({ manifest, day, close }: Props) {
  return (
    <dialog
      open
      className="sample-credits"
      aria-label="Sources and attribution"
    >
      <button onClick={close}>Close sources</button>
      <h2>Sources and attribution</h2>
      <p>
        Schedule simulation, not live. Weather is synthetic. Original 3D models
        are illustrative.
      </p>
      {manifest.attribution.map((source) => (
        <section key={source.name}>
          <h3>
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.name}
            </a>
          </h3>
          <p>{source.changes}</p>
          <a href={manifest.licence_url}>CC BY 4.0</a>
        </section>
      ))}
      <p>
        Dataset {manifest.version} · viewing {SAMPLE_DATES[day]}. No endorsement
        by source publishers is implied.
      </p>
      <p>
        DAM status is not an actual worksite location. Footprints are historical
        surveys; the sample clock does not reconstruct planning or buildings for
        that time.
      </p>
    </dialog>
  );
}
