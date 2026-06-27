import { useState } from "react";
import { convertUrl, exportEnriched, type DatasetData } from "../api";
import type { EditableMetadata } from "../metadata";

type Kind = "signals" | "images" | "any";
interface Fmt {
  label: string;
  fmt: string;
  ext: string;
  needs: Kind; // what data the format requires
  rec?: Kind[]; // dataset kinds this format is *recommended* for
}

// Which export formats suit which data — CSDM/JCAMP-DX for spectroscopy (1D signals); HDF5 for images.
const ALL_FORMATS: Fmt[] = [
  { label: "JCAMP-DX (.jdx)", fmt: "jcamp", ext: "jdx", needs: "signals", rec: ["signals"] },
  { label: "CSDM (.csdf)", fmt: "csdf", ext: "csdf", needs: "signals", rec: ["signals"] },
  { label: "HDF5 (.h5)", fmt: "h5", ext: "h5", needs: "any", rec: ["images"] },
  { label: "CSV — tidy", fmt: "csv", ext: "csv", needs: "signals" },
  { label: "Parquet", fmt: "parquet", ext: "parquet", needs: "signals" },
  { label: "Feather", fmt: "feather", ext: "feather", needs: "signals" },
  { label: "CSV per signal (.zip)", fmt: "zip", ext: "zip", needs: "signals" },
];

export function ExportMenu({
  url,
  name,
  technique,
  dataset,
  metadata,
}: {
  url: string;
  name: string;
  technique: string;
  dataset?: DatasetData;
  metadata?: EditableMetadata; // when provided, the export embeds these edits (enriched)
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const hasSignals = !dataset || (dataset.signals?.length ?? 0) > 0;
  const hasImages = (dataset?.images?.length ?? 0) > 0;
  const applies = (f: Fmt) =>
    f.needs === "any" || (f.needs === "signals" && hasSignals) || (f.needs === "images" && hasImages);
  const recommended = (f: Fmt) =>
    !!f.rec && ((hasSignals && f.rec.includes("signals")) || (hasImages && f.rec.includes("images")));

  const formats = ALL_FORMATS.filter(applies);
  const recs = formats.filter(recommended);
  const others = formats.filter((f) => !recommended(f));
  const stem = (metadata?.sample_name || name).replace(/\.[^.]+$/, "");

  async function download(f: Fmt) {
    setOpen(false);
    if (!metadata) {
      const a = document.createElement("a"); // plain export — direct GET download
      a.href = convertUrl(url, name, technique, f.fmt);
      a.download = `${stem}.${f.ext}`;
      a.click();
      return;
    }
    setBusy(f.fmt);
    try {
      const blob = await exportEnriched({ url, name, technique, fmt: f.fmt, metadata });
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `${stem}.${f.ext}`;
      a.click();
      URL.revokeObjectURL(href);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  const item = (f: Fmt) => (
    <button key={f.fmt} className="export-item" onClick={() => download(f)} disabled={busy === f.fmt}>
      {busy === f.fmt ? "…" : f.label}
      {recommended(f) && <span className="export-rec">recommended</span>}
    </button>
  );

  return (
    <div className="export-menu" onMouseLeave={() => setOpen(false)}>
      <button className="btn ghost sm" onClick={() => setOpen((o) => !o)}>
        {metadata ? "⬇ Export ▾" : "⬇ Convert ▾"}
      </button>
      {open && (
        <div className="export-dropdown">
          {recs.length > 0 && <div className="export-group">Recommended for {technique}</div>}
          {recs.map(item)}
          {others.length > 0 && recs.length > 0 && <div className="export-group">Other formats</div>}
          {others.map(item)}
        </div>
      )}
    </div>
  );
}
