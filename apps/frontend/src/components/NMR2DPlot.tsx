import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type { DatasetData } from "../api";

// A 2D NMR spectrum (COSY/HSQC/HMBC/…) as a contour over two chemical-shift axes. The backend sends a
// signed intensity grid with real ppm coordinates plus a suggested contour `level`/`max` (it spans a
// huge dynamic range, so we contour the magnitude above the noise floor). NMR convention: ppm axes
// increase right-to-left and bottom-to-top, so both are reversed.
export function NMR2DPlot({ dataset }: { dataset: DatasetData }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const im = dataset.images?.find((i) => i.kind === "nmr2d");
    if (!ref.current || !im?.values) return;
    const axisTitle = (a: { label: string; unit: string | null }) =>
      a.unit ? `${a.label} (${a.unit})` : a.label;

    const z = im.values.map((row) => row.map(Math.abs)); // contour the magnitude (peaks of either phase)
    const level = im.z.level ?? 1;
    const zmax = Math.max(im.z.max ?? level * 8, level * 1.5);

    const trace = {
      type: "contour",
      z,
      x: im.x.values,
      y: im.y.values,
      colorscale: "YlGnBu",
      reversescale: true,
      contours: { start: level, end: zmax, size: (zmax - level) / 10, coloring: "lines" },
      line: { width: 1 },
      showscale: false,
      hovertemplate: `${axisTitle(im.x)}: %{x:.2f}<br>${axisTitle(im.y)}: %{y:.2f}<extra></extra>`,
    };
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#c9d1d9", size: 12 },
      margin: { l: 64, r: 16, t: 12, b: 50 },
      xaxis: { title: { text: axisTitle(im.x), font: { size: 15 } }, tickfont: { size: 13 }, autorange: "reversed" },
      yaxis: { title: { text: axisTitle(im.y), font: { size: 15 } }, tickfont: { size: 13 }, autorange: "reversed" },
    };
    Plotly.react(ref.current, [trace] as never, layout as never, {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    });
  }, [dataset]);

  const im = dataset.images?.find((i) => i.kind === "nmr2d");
  return (
    <div>
      <div className="nmr2d-head">
        🧲 {(dataset.metadata.experiment as string) || "2D NMR"}
        {im && (
          <span className="mol-meta">
            {" "}
            · {im.shape[0]}×{im.shape[1]}
          </span>
        )}
      </div>
      <div ref={ref} style={{ width: "100%", height: 520 }} />
    </div>
  );
}
