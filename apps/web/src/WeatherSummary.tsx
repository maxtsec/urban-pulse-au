import { displayDateTime } from './city';
import type { WeatherSnapshot } from './city';

export function WeatherSummary({
  weather,
  onShowWeather,
}: {
  weather: WeatherSnapshot | null;
  onShowWeather: () => void;
}) {
  const reading = weather?.reading;
  return (
    <section className="weather-summary" aria-label="Weather summary">
      <div className="weather-summary-title">
        <h2>Modelled weather information</h2>
        <span>Southbank · Synthetic demo</span>
      </div>
      {reading ? (
        <>
          <dl className="weather-metrics">
            <div>
              <dt>Temperature</dt>
              <dd>
                {reading.temperature_c}
                <small> °C</small>
              </dd>
            </div>
            <div>
              <dt>Rainfall</dt>
              <dd>
                {reading.precipitation_mm}
                <small> mm</small>
              </dd>
            </div>
            <div>
              <dt>Wind</dt>
              <dd>
                {reading.wind_kmh}
                <small> km/h</small>
              </dd>
            </div>
          </dl>
          <p className="weather-summary-source">
            Modelled for {displayDateTime(reading.valid_at)} ·{' '}
            <a href={reading.source_url}>Open-Meteo</a> · Informational only;
            separate from warning coverage.
          </p>
        </>
      ) : weather ? (
        <p className="weather-summary-empty">
          No modelled weather reading received at this scenario time.
        </p>
      ) : (
        <div className="weather-summary-empty">
          <p>Weather information is not included in this transport scenario.</p>
          <button onClick={onShowWeather}>Show weather</button>
        </div>
      )}
    </section>
  );
}
