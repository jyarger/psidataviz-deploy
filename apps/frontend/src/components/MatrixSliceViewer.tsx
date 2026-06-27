import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import type { DatasetData, ImageData } from "../api";

// Interactive viewer for a 2D "matrix" image (e.g. an HPLC-DAD time x wavelength grid): a slider over the
// rows (wavelength) shows the corresponding 1D slice (the chromatogram at that wavelength), updated live.
export function MatrixSliceViewer({ dataset, image }: { dataset: DatasetData; image: ImageData }) {
  const ref = useRef<HTMLDivElement>(null);
  const rowCoords = image.y.values ?? [];
  const xCoords = image.x.values ?? [];

  // default the slider to 254 nm (a standard HPLC detection wavelength) when present
  const defaultRow = useMemo(() => {
    if (!rowCoords.length) return 0;
    let best = 0;
    let bestDist = Infinity;
    rowCoords.forEach((w, i) => {
      const d = Math.abs(w - 254);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    return best;
  }, [rowCoords]);

  const [row, setRow] = useState(defaultRow);
  useEffect(() => setRow(defaultRow), [defaultRow]);

  useEffect(() => {
    if (!ref.current || !image.values?.[row]) return;
    const traces = [
      {
        x: xCoords,
        y: image.values[row],
        type: "scattergl",
        mode: "lines",
        line: { color: "#4aa3ff", width: 1.4 },
        name: `${rowCoords[row]} ${image.y.unit ?? ""}`.trim(),
      },
    ];
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#c9d1d9", size: 12 },
      margin: { l: 64, r: 16, t: 12, b: 44 },
      xaxis: {
        title: { text: axisLabel(image.x), font: { size: 15 } },
        gridcolor: "#21262d",
        zeroline: false,
      },
      yaxis: {
        title: { text: axisLabel(image.z), font: { size: 15 } },
        gridcolor: "#21262d",
        zeroline: false,
      },
      showlegend: false,
    };
    Plotly.react(ref.current, traces as never, layout as never, {
      responsive: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    });
  }, [row, image, xCoords, rowCoords]);

  if (!rowCoords.length || !image.values?.length) return null;
  const label = (dataset.metadata.sample_name as string) || dataset.filename;

  return (
    <div className="matrix-card">
      <div className="matrix-head">
        🌈 {label} · DAD chromatogram
        <span className="mol-meta">
          {" "}
          · {image.shape[0]} wavelengths × {image.shape[1]} times
        </span>
      </div>
      <div ref={ref} className="matrix-plot" />
      <div className="matrix-slider">
        <span className="matrix-wl">
          {image.y.label}: <b>{rowCoords[row]} {image.y.unit}</b>
        </span>
        <input
          type="range"
          min={0}
          max={rowCoords.length - 1}
          value={row}
          onChange={(e) => setRow(Number(e.target.value))}
        />
        <span className="matrix-range muted">
          {rowCoords[0]}–{rowCoords[rowCoords.length - 1]} {image.y.unit}
        </span>
      </div>
    </div>
  );
}

function axisLabel(a: { label: string; unit: string | null }): string {
  return a.unit ? `${a.label} (${a.unit})` : a.label;
}
