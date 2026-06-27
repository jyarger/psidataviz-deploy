import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import type { DatasetData } from "../api";

type PlotMode = "lines" | "markers" | "lines+markers";
const MODE_LABEL: Record<PlotMode, string> = {
  lines: "Line",
  markers: "Points",
  "lines+markers": "Line + points",
};

const PALETTE = ["#4aa3ff", "#ff6b6b", "#51cf66", "#fcc419", "#b197fc", "#ff8787", "#22b8cf", "#a9e34b"];

// NMR & FTIR plot with a reversed abscissa by convention.
const REVERSED = new Set(["NMR", "FTIR"]);
// Mass spectra (standard MS and secondary-ion SIMS) are drawn as sticks, not a connected line.
const STICK = new Set(["Mass Spec", "SIMS"]);

function axisTitle(a: { label: string; unit: string | null }): string {
  return a.unit ? `${a.label} (${a.unit})` : a.label;
}

function normalizeY(ys: number[]): number[] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of ys) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  const span = hi - lo || 1;
  return ys.map((v) => (v - lo) / span);
}

export function SpectrumPlot({
  datasets,
  normalize = false,
  onPeakClick,
}: {
  datasets: DatasetData[];
  normalize?: boolean;
  onPeakClick?: (wavenumber: number, label: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<PlotMode>("lines");
  // mass spectra are sticks; the line/points toggle only applies to ordinary traces
  const showModes = datasets.some((d) => !STICK.has(d.technique));

  useEffect(() => {
    if (!ref.current || datasets.length === 0) return;
    const multi = datasets.length > 1;
    let color = 0;
    const traceLabels: string[] = []; // dataset label per trace (curveNumber -> sample), for click routing
    const traces = datasets.flatMap((ds) => {
      const label = ds.metadata.sample_name ? String(ds.metadata.sample_name) : ds.filename;
      const stick = STICK.has(ds.technique);
      return ds.signals.map((s) => {
        const segLabel = s.segment ?? s.name;
        const name = multi ? `${label} · ${segLabel}` : segLabel;
        const xs = s.points.map((p) => p[0]);
        const ysRaw = s.points.map((p) => p[1]);
        const ys = normalize ? normalizeY(ysRaw) : ysRaw;
        const clr = PALETTE[color++ % PALETTE.length];
        traceLabels.push(label);
        if (stick) {
          // draw each peak as a vertical line from baseline: x=[m,m,gap], y=[0,i,gap]
          const sx: (number | null)[] = [];
          const sy: (number | null)[] = [];
          for (let i = 0; i < xs.length; i++) {
            sx.push(xs[i], xs[i], null);
            sy.push(0, ys[i], null);
          }
          return {
            x: sx, y: sy, type: "scattergl", mode: "lines", name,
            line: { color: clr, width: 1 }, hoverinfo: "x+y" as const,
          };
        }
        return {
          x: xs, y: ys, type: "scattergl", mode, name,
          line: { color: clr, width: 1.4 },
          marker: { color: clr, size: 5 },
        };
      });
    });

    const x0 = datasets[0].signals[0]?.x;
    const y0 = datasets[0].signals[0]?.y;
    // when overlaid signals carry different units (e.g. a spreadsheet's strain+stress+modulus), don't
    // label the shared y-axis with just the first signal's name — it would be misleading.
    const yUnits = new Set(datasets.flatMap((d) => d.signals.map((s) => s.y.unit ?? "")).filter(Boolean));
    const yTitle = yUnits.size > 1
      ? (normalize ? "Value (normalized)" : "Value (mixed units)")
      : y0 ? (normalize ? `${y0.label} (normalized)` : axisTitle(y0)) : "";
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#c9d1d9", size: 12 },
      margin: { l: 64, r: 16, t: 12, b: 48 },
      xaxis: {
        title: { text: x0 ? axisTitle(x0) : "", font: { size: 16 } },
        tickfont: { size: 13 },
        type: x0?.scale === "log" ? "log" : undefined,
        autorange: REVERSED.has(datasets[0].technique) ? "reversed" : true,
        gridcolor: "#21262d",
        zeroline: false,
      },
      yaxis: {
        title: { text: yTitle, font: { size: 16 } },
        tickfont: { size: 13 },
        type: y0?.scale === "log" ? "log" : undefined,
        gridcolor: "#21262d",
        zeroline: false,
      },
      legend: { orientation: "h", y: -0.18 },
      showlegend: traces.length > 1,
    };
    Plotly.react(ref.current, traces as never, layout as never, {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    });

    if (onPeakClick) {
      // clicking a peak on a computed spectrum animates the nearest vibrational mode in the 3D viewer
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const el = ref.current as any;
      el.removeAllListeners?.("plotly_click");
      el.on("plotly_click", (e: { points?: { x: number; curveNumber: number }[] }) => {
        const p = e.points?.[0];
        if (p) onPeakClick(p.x, traceLabels[p.curveNumber] ?? "");
      });
    }
  }, [datasets, normalize, onPeakClick, mode]);

  return (
    <div>
      {showModes && (
        <div className="plot-modes">
          {(Object.keys(MODE_LABEL) as PlotMode[]).map((m) => (
            <button
              key={m}
              className={"plot-mode" + (mode === m ? " active" : "")}
              onClick={() => setMode(m)}
            >
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>
      )}
      <div ref={ref} style={{ width: "100%", height: 480 }} />
    </div>
  );
}
