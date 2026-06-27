import { useRef, useState } from "react";
import { api, type CatalogResult } from "../api";

type Collected = { file: File; path: string };

// Drag a local folder or .zip (or browse) to load local data. Files are uploaded to the backend, kept
// in memory for the session, and surfaced as a source in the workspace via an upload:// url.
export function DropZone({ onLoaded }: { onLoaded: (cat: CatalogResult & { url: string }) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const folderRef = useRef<HTMLInputElement>(null);
  const filesRef = useRef<HTMLInputElement>(null);

  async function send(files: Collected[]) {
    if (!files.length) {
      setErr("No files found in that drop.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      onLoaded(await api.upload(files));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setOver(false);
    const out: Collected[] = [];
    const entries = [...e.dataTransfer.items]
      .map((i) => i.webkitGetAsEntry?.())
      .filter(Boolean) as FileSystemEntry[];
    if (entries.length) {
      for (const entry of entries) await readEntry(entry, "", out);
    } else {
      for (const f of e.dataTransfer.files) out.push({ file: f, path: f.name });
    }
    await send(out);
  }

  function fromInput(list: FileList | null) {
    if (!list) return;
    const out = [...list].map((f) => ({
      file: f,
      path: (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name,
    }));
    void send(out);
  }

  return (
    <div
      className={"dropzone" + (over ? " over" : "")}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <div className="dz-icon">
        <span className="psi">Ψ</span> ⬆
      </div>
      <div className="dz-text">
        {busy ? "Uploading & scanning…" : "Drag a folder or .zip here to load local data"}
      </div>
      <div className="dz-actions">
        <button className="btn ghost sm" onClick={() => folderRef.current?.click()} disabled={busy}>
          Choose folder
        </button>
        <button className="btn ghost sm" onClick={() => filesRef.current?.click()} disabled={busy}>
          Choose files / zip
        </button>
      </div>
      {/* webkitdirectory enables folder selection; not in the standard input typings */}
      <input
        ref={folderRef}
        type="file"
        multiple
        hidden
        {...({ webkitdirectory: "" } as Record<string, string>)}
        onChange={(e) => fromInput(e.target.files)}
      />
      <input ref={filesRef} type="file" multiple hidden onChange={(e) => fromInput(e.target.files)} />
      {err && <p className="error">{err}</p>}
      <p className="muted dz-note">Read in memory for this session — not saved to disk.</p>
    </div>
  );
}

async function readEntry(entry: FileSystemEntry, prefix: string, out: Collected[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) =>
      (entry as FileSystemFileEntry).file(res, rej),
    );
    out.push({ file, path: prefix + entry.name });
  } else if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    let batch: FileSystemEntry[];
    do {
      batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
      for (const e of batch) await readEntry(e, `${prefix}${entry.name}/`, out);
    } while (batch.length);
  }
}
