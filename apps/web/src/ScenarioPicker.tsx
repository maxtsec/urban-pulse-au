export const scenarios = [
  { id: 'city', label: 'City overview' },
  { id: 'planning-outage', label: 'Planning outage' },
  { id: 'weather', label: 'Weather warnings' },
  { id: 'journey', label: 'Tram journey' },
  { id: 'weather-outage', label: 'Weather outage' },
  { id: 'outage', label: 'Transport outage' },
  { id: 'empty', label: 'Empty transport' },
];

export function initialScenario() {
  const requested = new URLSearchParams(window.location.search).get('scenario');
  return scenarios.find((item) => item.id === requested)?.id ?? 'city';
}

export function ScenarioPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="scenario-switcher" role="group" aria-label="Scenario">
      <span className="scenario-label">Explore a scenario</span>
      <div className="scenario-buttons">
        {scenarios.map((scenario) => (
          <button
            key={scenario.id}
            type="button"
            aria-pressed={value === scenario.id}
            onClick={() => onChange(scenario.id)}
          >
            {scenario.label}
          </button>
        ))}
      </div>
    </div>
  );
}
