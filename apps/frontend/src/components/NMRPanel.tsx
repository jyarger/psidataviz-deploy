import { useState } from "react";
import type { DatasetData } from "../api";
import { categorizeNMR, expName } from "../nmr";
import { SpectrumPlot } from "./SpectrumPlot";
import { NMR2DPlot } from "./NMR2DPlot";
import { LayoutTabs } from "./LayoutTabs";

// A unified, NMRium-style view of a compound's NMR data: tabs by nucleus (1D: ¹H, ¹³C, …) and nucleus
// pair (2D: ¹H–¹H COSY, ¹H–¹³C HSQC/HMBC, …). 1D experiments of the same nucleus overlay (so ¹³C +
// DEPT compare directly); 2D experiments render as contours, sub-tabbed when several share a pair.
export function NMRPanel({
  datasets,
  normalize,
  onPeak,
}: {
  datasets: DatasetData[];
  normalize: boolean;
  onPeak: (freq: number, label: string) => void;
}) {
  const tabs = categorizeNMR(datasets);
  const [active, setActive] = useState(0);
  if (tabs.length === 0) return null;
  const idx = Math.min(active, tabs.length - 1);
  const tab = tabs[idx];

  return (
    <div className="nmr-panel">
      {tabs.length > 1 && (
        <div className="nmr-tabs" role="tablist">
          {tabs.map((t, i) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={i === idx}
              className={"nmr-tab" + (i === idx ? " active" : "")}
              onClick={() => setActive(i)}
            >
              {t.label}
              {t.is2d && <span className="nmr-2d-badge">2D</span>}
              {t.datasets.length > 1 && <span className="nmr-count">{t.datasets.length}</span>}
            </button>
          ))}
        </div>
      )}
      <div className="nmr-tab-body">
        {tab.is2d ? (
          tab.datasets.length === 1 ? (
            <NMR2DPlot dataset={tab.datasets[0]} />
          ) : (
            <LayoutTabs
              items={tab.datasets.map((ds) => ({
                key: ds.filename,
                label: expName(ds),
                node: <NMR2DPlot dataset={ds} />,
              }))}
            />
          )
        ) : (
          <SpectrumPlot datasets={tab.datasets} normalize={normalize} onPeakClick={onPeak} />
        )}
      </div>
    </div>
  );
}
