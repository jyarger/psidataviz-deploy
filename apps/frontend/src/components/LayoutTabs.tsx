import { useState, type ReactNode } from "react";

export type LayoutMode = "tabs" | "grid" | "stack";
export interface LayoutItem {
  key: string;
  label: string;
  node: ReactNode;
}

const MODE_ICON: Record<LayoutMode, string> = { tabs: "▭ Tabs", grid: "▦ Grid", stack: "☰ Stack" };

// Lay out several viz items as tabs (default), a grid, or a vertical stack. With a single item it just
// renders it; the layout selector appears only when there's more than one.
export function LayoutTabs({ items }: { items: LayoutItem[] }) {
  const [mode, setMode] = useState<LayoutMode>("tabs");
  const [active, setActive] = useState(0);
  if (items.length === 0) return null;
  if (items.length === 1) return <>{items[0].node}</>;

  const idx = Math.min(active, items.length - 1);
  return (
    <div className="layout-panel">
      <div className="layout-bar">
        {mode === "tabs" ? (
          <div className="layout-tabs">
            {items.map((it, i) => (
              <button
                key={it.key}
                className={"layout-tab" + (i === idx ? " active" : "")}
                onClick={() => setActive(i)}
                title={it.label}
              >
                {it.label}
              </button>
            ))}
          </div>
        ) : (
          <span className="muted">{items.length} items</span>
        )}
        <div className="layout-modes">
          {(["tabs", "grid", "stack"] as LayoutMode[]).map((m) => (
            <button
              key={m}
              className={"layout-mode" + (mode === m ? " active" : "")}
              onClick={() => setMode(m)}
            >
              {MODE_ICON[m]}
            </button>
          ))}
        </div>
      </div>
      {mode === "tabs" && <div className="layout-body">{items[idx].node}</div>}
      {mode === "grid" && (
        <div className="layout-grid">
          {items.map((it) => (
            <div key={it.key} className="layout-cell">
              {it.node}
            </div>
          ))}
        </div>
      )}
      {mode === "stack" && items.map((it) => <div key={it.key}>{it.node}</div>)}
    </div>
  );
}
