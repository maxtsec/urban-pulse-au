import { displayDateTime } from './city';
import type { WeatherSnapshot } from './city';

/** Compact modelled reading shown on the map; it never changes warning coverage. */
export function WeatherSummary({
  weather,
}: {
  weather: WeatherSnapshot | null;
}) {
  const reading = weather?.reading;
  return (
    <section
      className="chip weather-chip"
      aria-label="Weather summary"
      title={
        reading
          ? `Modelled for ${displayDateTime(reading.valid_at)} by Open-Meteo. Informational only; separate from warning coverage.`
          : undefined
      }
    >
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M6 15h8a3.5 3.5 0 0 0 .4-7A5 5 0 0 0 5 9a3 3 0 0 0 1 6z"
          fill="none"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
      {reading ? (
        <>
          <span className="chip-caption">Modelled</span>
          <span className="weather-values">
            <strong>{reading.temperature_c} °C</strong>
            <span>{reading.precipitation_mm} mm</span>
            <span>{reading.wind_kmh} km/h</span>
          </span>
        </>
      ) : weather ? (
        <span>No modelled weather reading received</span>
      ) : (
        <span>Weather not included in this transport scenario</span>
      )}
    </section>
  );
}
