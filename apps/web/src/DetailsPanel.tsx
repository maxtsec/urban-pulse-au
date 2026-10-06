import { useRef } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';

export type Tab = 'overview' | 'trams' | 'developments' | 'warnings';

type Props = {
  tabs: { id: Tab; label: string; count?: number }[];
  active: Tab;
  onSelect: (tab: Tab) => void;
  onHide: () => void;
  children: ReactNode;
};

/** The single side panel: one tab of detail at a time beside the map. */
export function DetailsPanel({
  tabs,
  active,
  onSelect,
  onHide,
  children,
}: Props) {
  const buttons = useRef<Map<Tab, HTMLButtonElement>>(new Map());
  function move(event: KeyboardEvent, index: number) {
    const step =
      event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = tabs[(index + step + tabs.length) % tabs.length];
    onSelect(next.id);
    buttons.current.get(next.id)?.focus();
  }
  return (
    <aside className="details-panel" aria-label="City details">
      <div className="details-header">
        <div className="tabs" role="tablist" aria-label="Detail sections">
          {tabs.map((tab, index) => (
            <button
              key={tab.id}
              ref={(node) => {
                if (node) buttons.current.set(tab.id, node);
                else buttons.current.delete(tab.id);
              }}
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={active === tab.id}
              aria-controls="details-tabpanel"
              tabIndex={active === tab.id ? 0 : -1}
              onClick={() => onSelect(tab.id)}
              onKeyDown={(event) => move(event, index)}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="tab-count">{tab.count}</span>
              )}
            </button>
          ))}
        </div>
        <button
          className="icon-button hide-panel"
          aria-label="Hide details"
          title="Hide details"
          onClick={onHide}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M8 5l5 5-5 5"
              fill="none"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>
      <div
        className="details-body"
        role="tabpanel"
        id="details-tabpanel"
        aria-labelledby={`tab-${active}`}
      >
        {children}
      </div>
    </aside>
  );
}
