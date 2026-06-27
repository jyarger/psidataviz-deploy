import { useCallback, useEffect, useRef, useState } from "react";
import * as $3Dmol from "3dmol";
import { api, type MoleculeData } from "../api";

// A self-contained 3D molecule viewer: type a SMILES or a compound name (resolved via the backend +
// PubChem) and see its structure. Auto-loads a guessed compound when one is supplied.
export function CompoundViewer({ initialQuery }: { initialQuery?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewerRef = useRef<any>(null);
  const [query, setQuery] = useState(initialQuery ?? "");
  const [mol, setMol] = useState<MoleculeData | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [spin, setSpin] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let viewer: any;
    try {
      viewer = $3Dmol.createViewer(el, { backgroundColor: "#0d1117" });
      viewerRef.current = viewer;
    } catch {
      /* WebGL unavailable */
    }
    const onResize = () => viewer?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      try {
        viewer?.clear();
      } catch {
        /* noop */
      }
      if (el) el.innerHTML = "";
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !mol) return;
    viewer.removeAllModels();
    viewer.addModel(mol.molblock, "sdf");
    viewer.setStyle({}, { stick: { radius: 0.13 }, sphere: { scale: 0.27 } });
    viewer.zoomTo();
    viewer.spin(spin ? "y" : false);
    viewer.render();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mol]);

  const load = useCallback(async (term: string) => {
    const t = term.trim();
    if (!t) return;
    setStatus("loading");
    try {
      setMol(await api.molecule(t));
      setStatus("idle");
    } catch {
      setMol(null);
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
      load(initialQuery);
    }
  }, [initialQuery, load]);

  function toggleSpin() {
    const next = !spin;
    setSpin(next);
    viewerRef.current?.spin(next ? "y" : false);
  }

  return (
    <div className="mol-card">
      <div className="mol-head">
        <span className="mol-title">🧬 Molecule viewer</span>
        {mol && (
          <button className="mol-spin" onClick={toggleSpin}>
            {spin ? "Stop" : "Spin"}
          </button>
        )}
      </div>
      <form
        className="mol-search"
        onSubmit={(e) => {
          e.preventDefault();
          load(query);
        }}
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="SMILES or compound name — e.g. aspirin, caffeine, c1ccccc1C=O"
          spellCheck={false}
        />
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "…" : "Show"}
        </button>
      </form>
      {mol && (
        <div className="mol-info">
          {mol.formula && <b>{mol.formula}</b>}
          {mol.iupac && <span className="mol-iupac"> · {mol.iupac}</span>}
          <span className="mol-smiles"> · {mol.smiles}</span>
          {mol.cid && (
            <>
              {" · "}
              <a href={`https://pubchem.ncbi.nlm.nih.gov/compound/${mol.cid}`} target="_blank" rel="noreferrer">
                PubChem
              </a>
            </>
          )}
        </div>
      )}
      {status === "error" && (
        <div className="mol-empty">No match for “{query}”. Try a SMILES string or a different name.</div>
      )}
      <div ref={ref} className="mol-canvas" style={{ display: mol ? "block" : "none" }} />
      {!mol && status !== "error" && (
        <div className="mol-empty">Type a SMILES or a compound name to see its 3D structure.</div>
      )}
    </div>
  );
}
