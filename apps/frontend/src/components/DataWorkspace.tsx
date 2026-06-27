import { useState } from "react";
import { api, type CatalogResult, type DatasetData, type RecordRow } from "../api";
import { SpectrumPlot } from "./SpectrumPlot";
import { Heatmap } from "./Heatmap";
import { NMRPanel } from "./NMRPanel";
import { LayoutTabs } from "./LayoutTabs";
import { MoleculeViewer } from "./MoleculeViewer";
import { WaveformPlayer } from "./WaveformPlayer";
import { DropZone } from "./DropZone";
import { MetadataPanel } from "./MetadataPanel";
import { ExportMenu } from "./ExportMenu";
import { deriveMetadata, type EditableMetadata } from "../metadata";

type Source = { url: string; label: string; icon: string; catalog: CatalogResult };
type Row = RecordRow & { source: string; ckey: string };

const PRESETS = [
  { url: "https://github.com/yargerlab/Data", icon: "GH", label: "yargerlab/Data" },
  {
    url: "https://drive.google.com/drive/folders/16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4",
    icon: "GD",
    label: "Google Drive — Psi_Data",
  },
  { url: "https://codeberg.org/jyarger/PsiData", icon: "CB", label: "Codeberg — PsiData" },
  {
    url: "https://app.box.com/s/yigbg0fd5xj5n1hkxf8rcsemrkz7qgsx",
    icon: "BX",
    label: "Box — PsiData",
  },
  { url: "https://www.chemotion-repository.net/", icon: "CT", label: "Chemotion — published data" },
];

function labelFor(url: string, source: string): { label: string; icon: string } {
  if (source.startsWith("github:")) return { label: source.slice(7), icon: "GH" };
  if (source.startsWith("gdrive:")) return { label: "Google Drive", icon: "GD" };
  return { label: source, icon: "•" };
}

export function DataWorkspace() {
  const [input, setInput] = useState("");
  const [keyword, setKeyword] = useState(""); // optional path keyword to limit a large scan
  const [sources, setSources] = useState<Source[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tech, setTech] = useState<string | null>(null);
  const [srcFilter, setSrcFilter] = useState<string | null>(null);
  const [needle, setNeedle] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [datasets, setDatasets] = useState<Record<string, DatasetData>>({});
  const [normalize, setNormalize] = useState(false);
  const [peak, setPeak] = useState<{ freq: number; label: string } | null>(null);
  const [metaEdits, setMetaEdits] = useState<Record<string, EditableMetadata>>({});

  async function addSource(url: string) {
    const u = url.trim();
    if (!u) return;
    if (sources.some((s) => s.url === u)) {
      setError("That source is already added.");
      return;
    }
    setBusy(`Scanning ${u} …`);
    setError(null);
    try {
      const catalog = await api.catalog(u, keyword);
      const { label, icon } = labelFor(u, catalog.source);
      setSources((s) => [...s, { url: u, label, icon, catalog }]);
      setInput("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function addUploaded(cat: CatalogResult & { url: string }) {
    setError(null);
    if (sources.some((s) => s.url === cat.url)) return;
    setSources((s) => [...s, { url: cat.url, label: cat.source, icon: "⬆", catalog: cat }]);
  }

  function removeSource(url: string) {
    const gone = sources.find((s) => s.url === url);
    setSources((s) => s.filter((x) => x.url !== url));
    if (gone) {
      setSelected((sel) => sel.filter((k) => !k.startsWith(url + "|")));
      setDatasets((d) => Object.fromEntries(Object.entries(d).filter(([k]) => !k.startsWith(url + "|"))));
      if (srcFilter === gone.label) setSrcFilter(null);
    }
  }

  const rows: Row[] = sources.flatMap((s) =>
    s.catalog.records.map((r) => ({ ...r, source: s.label, ckey: `${s.url}|${r.uid}` })),
  );
  const techniques = [...new Set(rows.map((r) => r.technique))].sort();
  const nd = needle.trim().toLowerCase();
  const shown = rows.filter(
    (r) =>
      (!tech || r.technique === tech) &&
      (!srcFilter || r.source === srcFilter) &&
      (!nd ||
        r.description.toLowerCase().includes(nd) ||
        r.name.toLowerCase().includes(nd) ||
        (r.date ?? "").includes(nd)),
  );

  async function toggle(r: Row) {
    if (selected.includes(r.ckey)) {
      setSelected((s) => s.filter((k) => k !== r.ckey));
      setDatasets((d) => {
        const next = { ...d };
        delete next[r.ckey];
        return next;
      });
      return;
    }
    setBusy(`Loading ${r.name} …`);
    setError(null);
    try {
      const ds = await api.dataset(r.url, r.name, r.technique, r.sidecar_url);
      setSelected((s) => [...s, r.ckey]);
      setDatasets((d) => ({ ...d, [r.ckey]: ds }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const selectedDatasets = selected.map((k) => datasets[k]).filter(Boolean);
  const audioDatasets = selectedDatasets.filter((d) => d.audio);
  const nmrDatasets = selectedDatasets.filter((d) => d.technique === "NMR");
  const signalDatasets = selectedDatasets.filter(
    (d) => d.signals?.length > 0 && !d.audio && d.technique !== "NMR",
  );
  const imageDatasets = selectedDatasets.filter((d) => d.images?.length > 0 && d.technique !== "NMR");

  return (
    <>
      <h1>Multi-source data workspace</h1>
      <p className="subtitle">
        Add several public sources, then filter and overlay datasets across all of them.
      </p>

      <div className="row">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addSource(input)}
          placeholder="Add a GitHub repo or public Google Drive folder URL"
        />
        <input
          type="text"
          className="filter kw"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addSource(input)}
          placeholder="keyword filter (optional)"
          title="Only scan files whose path contains this — useful for very large repos"
        />
        <button className="btn" onClick={() => addSource(input)} disabled={!!busy}>
          + Add source
        </button>
      </div>
      <div className="presets">
        <span className="muted">Quick add:</span>
        {PRESETS.filter((p) => !sources.some((s) => s.url === p.url)).map((p) => (
          <button key={p.url} className="src-chip" onClick={() => addSource(p.url)} disabled={!!busy}>
            <span className="src-ic">{p.icon}</span>
            {p.label}
          </button>
        ))}
      </div>

      <DropZone onLoaded={addUploaded} />

      {busy && <p className="spinner">{busy}</p>}
      {error && <p className="error">{error}</p>}

      {sources.length === 0 && !busy && (
        <div className="card">
          <p className="coming" style={{ padding: "24px 0" }}>
            Add one or more public sources above to build a combined, filterable catalog.
          </p>
        </div>
      )}

      {sources.length > 0 && (
        <div className="card with-brand">
          <PanelBrand label="PsiData" />
          <div className="toolbar">
            <span className="section-title" style={{ margin: 0 }}>
              {rows.length.toLocaleString()} datasets across {sources.length} source
              {sources.length === 1 ? "" : "s"}
            </span>
          </div>

          <div className="chips" style={{ marginBottom: 12 }}>
            {sources.map((s) => (
              <span
                key={s.url}
                className={"chip" + (s.label === srcFilter ? " active" : "")}
                onClick={() => setSrcFilter(srcFilter === s.label ? null : s.label)}
              >
                <span className="src-ic" style={{ width: 18, height: 18, marginRight: 6 }}>{s.icon}</span>
                {s.label}
                <span className="count">{s.catalog.records.length}</span>
                <span
                  className="chip-x"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeSource(s.url);
                  }}
                  title="Remove source"
                >
                  ×
                </span>
              </span>
            ))}
          </div>

          <div className="chips">
            {techniques.map((t) => (
              <span
                key={t}
                className={"chip" + (t === tech ? " active" : "")}
                onClick={() => setTech(tech === t ? null : t)}
              >
                {t}
                <span className="count">{rows.filter((r) => r.technique === t).length}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {sources.length > 0 && (
        <div className="card">
          <div className="toolbar">
            <span className="section-title" style={{ margin: 0 }}>
              {shown.length} of {rows.length} datasets{" "}
              <span className="muted">— click to overlay</span>
            </span>
            <input
              type="text"
              className="filter"
              value={needle}
              onChange={(e) => setNeedle(e.target.value)}
              placeholder="filter by sample, date…"
            />
          </div>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Technique</th>
                  <th>Compound</th>
                  <th>Date</th>
                  <th>Sample / description</th>
                  <th>Formats</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr
                    key={r.ckey}
                    className={selected.includes(r.ckey) ? "selected" : ""}
                    onClick={() => toggle(r)}
                  >
                    <td className="muted">{r.source}</td>
                    <td>{r.technique}</td>
                    <td>{r.compound ? <span className="compound-tag">{r.compound}</span> : ""}</td>
                    <td>{r.date ?? "—"}</td>
                    <td>{r.description}</td>
                    <td className="fmt">{r.formats.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selectedDatasets.length > 0 && (
        <div className="card with-brand">
          <PanelBrand label="PsiViz" />
          <div className="toolbar">
            <span className="section-title" style={{ margin: 0 }}>
              {selectedDatasets.length} dataset{selectedDatasets.length === 1 ? "" : "s"} overlaid
            </span>
            <div className="row" style={{ gap: 12 }}>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={normalize}
                  onChange={(e) => setNormalize(e.target.checked)}
                />
                Normalize
              </label>
              <button
                className="btn ghost"
                onClick={() => {
                  setSelected([]);
                  setDatasets({});
                }}
              >
                Clear
              </button>
            </div>
          </div>
          {nmrDatasets.length > 0 && (
            <NMRPanel
              datasets={nmrDatasets}
              normalize={normalize}
              onPeak={(freq, label) => setPeak({ freq, label })}
            />
          )}
          {signalDatasets.length > 0 && (
            <SpectrumPlot
              datasets={signalDatasets}
              normalize={normalize}
              onPeakClick={(freq, label) => setPeak({ freq, label })}
            />
          )}
          <LayoutTabs
            items={imageDatasets.map((ds) => ({
              key: ds.filename,
              label: (ds.metadata.sample_name as string) || ds.filename,
              node: <Heatmap dataset={ds} />,
            }))}
          />
          {selectedDatasets
            .filter((d) => d.structure)
            .map((ds) => (
              <MoleculeViewer
                key={`mol-${ds.filename}`}
                structure={ds.structure!}
                title={(ds.metadata.sample_name as string) || ds.filename}
                peak={peak}
              />
            ))}
          {audioDatasets.map((ds) => (
            <WaveformPlayer key={`wav-${ds.filename}`} dataset={ds} />
          ))}
          {selected
            .map((k) => [k, datasets[k], rows.find((r) => r.ckey === k)] as const)
            .filter(([, ds]) => ds)
            .map(([k, ds, row]) => {
              const md = metaEdits[k] ?? deriveMetadata(ds);
              return (
                <div key={`md-${k}`}>
                  <MetadataPanel
                    dataset={ds}
                    value={metaEdits[k]}
                    onChange={(m) => setMetaEdits((prev) => ({ ...prev, [k]: m }))}
                  />
                  {row && (
                    <div className="export-row">
                      <span className="muted">Export with this metadata:</span>
                      <ExportMenu
                        url={row.url}
                        name={row.name}
                        technique={row.technique}
                        dataset={ds}
                        metadata={md}
                      />
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </>
  );
}

function PanelBrand({ label }: { label: string }) {
  return (
    <div className="panel-brand">
      <span className="psi">Ψ</span>
      {label}
    </div>
  );
}
