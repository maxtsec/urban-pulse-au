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
    <label className="chip scenario-picker">
      <span className="chip-caption">Scenario</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {scenarios.map((scenario) => (
          <option key={scenario.id} value={scenario.id}>
            {scenario.label}
          </option>
        ))}
      </select>
    </label>
  );
}
