import { useEffect, useRef, useState } from "react";
import * as $3Dmol from "3dmol";
import type { StructureData } from "../api";

// 3D molecular / crystal structure, rendered by 3Dmol.js from the raw structure-file text the backend
// ships. Drag to rotate, scroll to zoom. For a frequency calculation, each vibrational normal mode can
// be animated (every atom oscillates along its displacement vector).
export function MoleculeViewer({
  structure,
  title,
  peak,
}: {
  structure: StructureData;
  title: string;
  peak?: { freq: number; label: string } | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewerRef = useRef<any>(null);
  const [mode, setMode] = useState(-1); // -1 = static (no animation)
  const [spin, setSpin] = useState(false);
  const [error, setError] = useState(false);
  const modes = structure.modes ?? [];

  // (Re)draw the molecule; if modeIndex >= 0, animate that normal mode.
  const draw = (modeIndex: number) => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    try {
      viewer.stopAnimate();
    } catch {
      /* noop */
    }
    viewer.removeAllModels();
    const model = viewer.addModel(structure.data, structure.format);
    viewer.setStyle({}, { stick: { radius: 0.13 }, sphere: { scale: 0.27 } });
    viewer.zoomTo();
    const m = modeIndex >= 0 ? modes[modeIndex] : null;
    if (m) {
      // attach each atom's displacement vector, then let 3Dmol build oscillation frames
      const atoms = model.selectedAtoms({});
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      atoms.forEach((a: any, i: number) => {
        const d = m.disps[i];
        if (d) [a.dx, a.dy, a.dz] = d;
      });
      viewer.vibrate(12, 1.6, true);
      viewer.animate({ loop: "backAndForth", interval: 60 });
    }
    viewer.spin(modeIndex < 0 && spin ? "y" : false);
    viewer.render();
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let viewer: any;
    try {
      viewer = $3Dmol.createViewer(el, { backgroundColor: "#0d1117" });
      viewerRef.current = viewer;
      setMode(-1);
      draw(-1);
    } catch {
      setError(true);
    }
    const onResize = () => viewer?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      try {
        viewer?.stopAnimate();
        viewer?.clear();
      } catch {
        /* noop */
      }
      if (el) el.innerHTML = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure]);

  // a peak clicked on this molecule's spectrum -> animate the nearest vibrational mode
  useEffect(() => {
    if (!peak || peak.label !== title || modes.length === 0) return;
    let best = -1;
    let bestDist = Infinity;
    modes.forEach((m, i) => {
      const d = Math.abs(m.freq - peak.freq);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    if (best >= 0 && bestDist < 80) selectMode(best);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [peak]);

  function selectMode(idx: number) {
    setMode(idx);
    draw(idx);
  }
  function toggleSpin() {
    const next = !spin;
    setSpin(next);
    viewerRef.current?.spin(next ? "y" : false);
  }

  return (
    <div className="mol-card">
      <div className="mol-head">
        <span className="mol-title">
          🧬 {title}
          {structure.n_atoms != null && <span className="mol-meta"> · {structure.n_atoms} atoms</span>}
          <span className="mol-meta"> · {structure.format.toUpperCase()}</span>
        </span>
        {!error &&
          (modes.length > 0 ? (
            <label className="mol-modesel" title="…or click a peak on the spectrum above">
              Vibration:
              <select value={mode} onChange={(e) => selectMode(Number(e.target.value))}>
                <option value={-1}>none</option>
                {modes.map((m, i) => (
                  <option key={i} value={i}>
                    {m.freq.toFixed(0)} cm⁻¹{m.ir != null ? ` · IR ${m.ir}` : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <button className="mol-spin" onClick={toggleSpin}>
              {spin ? "Stop" : "Spin"}
            </button>
          ))}
      </div>
      {error ? (
        <div className="mol-fallback">
          3D view unavailable (WebGL not supported here). {structure.n_atoms ?? "?"} atoms ·{" "}
          {structure.format.toUpperCase()} structure.
        </div>
      ) : (
        <div ref={ref} className="mol-canvas" />
      )}
    </div>
  );
}
