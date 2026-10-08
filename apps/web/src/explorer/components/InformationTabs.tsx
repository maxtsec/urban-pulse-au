export type InformationPage = 'health' | 'weather' | 'trams' | 'works';

type Props = {
  detail: InformationPage;
  setDetail: (page: InformationPage) => void;
};

export function InformationTabs({ detail, setDetail }: Props) {
  return (
    <div
      className="info-tabs"
      role="tablist"
      aria-label="Area information pages"
    >
      {(
        [
          { id: 'health', label: 'Area health' },
          { id: 'weather', label: 'Weather' },
          { id: 'trams', label: 'Trams' },
          { id: 'works', label: 'Works' },
        ] as const
      ).map((tab) => (
        <button
          key={tab.id}
          id={`tab-${tab.id}`}
          role="tab"
          aria-selected={detail === tab.id}
          aria-controls="information-content"
          tabIndex={detail === tab.id ? 0 : -1}
          onClick={() => setDetail(tab.id)}
          onKeyDown={(event) => {
            const tabs = ['health', 'weather', 'trams', 'works'] as const;
            let index = tabs.indexOf(detail);
            if (event.key === 'ArrowRight') index = (index + 1) % 4;
            else if (event.key === 'ArrowLeft') index = (index + 3) % 4;
            else if (event.key === 'Home') index = 0;
            else if (event.key === 'End') index = 3;
            else return;
            event.preventDefault();
            setDetail(tabs[index]);
            document.getElementById(`tab-${tabs[index]}`)?.focus();
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
