// Typed client for the PsiData FastAPI backend (proxied at /api in dev).

export interface Technique {
  technique: string;
  n_datasets: number;
  n_supported: number;
}
export interface UnreadFormat {
  ext: string;
  count: number;
  note?: string;
  hint?: string;
}
export interface UnreadItem {
  name: string;
  technique: string;
  formats: string[];
  reason: string;
  hint?: string | null;
}
export interface Diagnostics {
  coverage: number;
  n_supported: number;
  n_unsupported: number;
  unread_formats: UnreadFormat[];
  unread_by_technique: { technique: string; count: number }[];
  unread_items: UnreadItem[];
}
export interface Compound {
  compound: string;
  n_supported: number;
}
export interface Organization {
  kind: "technique" | "sample" | "mixed" | "unstructured" | "empty";
  by_technique: number;
  by_sample: number;
  unstructured: number;
  total: number;
}
export interface ScanResult {
  source: string;
  n_files: number;
  n_records: number;
  n_data_records: number;
  n_supported_records: number;
  techniques: Technique[];
  compounds: Compound[];
  organization: Organization;
  diagnostics: Diagnostics;
}
export interface RecordRow {
  key: string;
  uid: string;
  technique: string;
  compound: string;
  date: string | null;
  description: string;
  formats: string[];
  extras: string[];
  primary: string;
  name: string;
  url: string;
  sidecar_url: string | null;
}
export interface CatalogResult extends ScanResult {
  records: RecordRow[];
}
export interface AxisInfo {
  label: string;
  unit: string | null;
  quantity: string | null;
  scale?: string | null; // "log" => show this axis logarithmically
}
export interface SignalData {
  name: string;
  segment: string | null;
  x: AxisInfo;
  y: AxisInfo;
  points: [number, number][];
}
export interface ImageData {
  name: string;
  kind?: "map" | "photo" | "matrix" | "nmr2d";
  data_uri?: string; // for kind === "photo": a PNG data URI of the micrograph
  // for kind === "matrix"/"nmr2d", x/y carry their real coordinate values (ppm, retention times, …)
  x: { label: string; unit: string | null; values?: number[] };
  y: { label: string; unit: string | null; values?: number[] };
  z: { label: string; unit: string | null; scale?: string; level?: number; max?: number };
  shape: [number, number];
  values?: number[][]; // the grid: kind "map" = heatmap intensities, "matrix" = rows sliced by the UI
}
export interface VibModeData {
  freq: number;
  ir: number | null;
  raman: number | null;
  disps: [number, number, number][];
}
export interface StructureData {
  data: string;
  format: string;
  title: string | null;
  n_atoms: number | null;
  modes: VibModeData[];
}
export interface ZipMember {
  key: string;
  member: string | null;
  formats: string[];
}
export interface AudioData {
  sample_rate: number;
  n_samples: number;
  channels: number;
  duration: number;
}
export interface DatasetData {
  technique: string;
  filename: string;
  reader: string;
  metadata: Record<string, unknown>;
  signals: SignalData[];
  images: ImageData[];
  structure: StructureData | null;
  audio?: AudioData | null;
  audio_url?: string | null;
  bundle?: { members: ZipMember[]; current: string | null };
}

export interface FormatComparison {
  identical?: boolean;
  summary?: string;
  differences?: string[];
  error?: string;
}
export interface CompareResult {
  comparable: boolean;
  reason?: string;
  technique?: string;
  primary?: string;
  formats: string[];
  comparisons?: Record<string, FormatComparison>;
  summary?: string;
}

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(b.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

const q = encodeURIComponent;

export interface MoleculeData {
  molblock: string;
  smiles: string;
  query: string;
  iupac?: string | null;
  formula?: string | null;
  cid?: number | null;
  cas?: string | null;
  svg?: string | null; // a 2D structure depiction
}

const flt = (kw?: string) => (kw && kw.trim() ? `&filter=${q(kw.trim())}` : "");

export const api = {
  scan: (url: string, keyword?: string) => get<ScanResult>(`/api/scan?url=${q(url)}${flt(keyword)}`),
  molecule: (query: string) => get<MoleculeData>(`/api/molecule?q=${q(query)}`),
  catalog: (url: string, keyword?: string) =>
    get<CatalogResult>(`/api/catalog?url=${q(url)}${flt(keyword)}`),
  records: (url: string, technique: string, keyword?: string) =>
    get<RecordRow[]>(`/api/records?url=${q(url)}&technique=${q(technique)}${flt(keyword)}`),
  dataset: (
    url: string,
    name: string,
    technique: string,
    sidecarUrl?: string | null,
    member?: string | null,
  ) =>
    get<DatasetData>(
      `/api/dataset?url=${q(url)}&name=${q(name)}&technique=${q(technique)}` +
        (sidecarUrl ? `&sidecar_url=${q(sidecarUrl)}` : "") +
        (member ? `&member=${q(member)}` : ""),
    ),
  compare: (url: string, technique: string, key: string) =>
    post<CompareResult>(`/api/compare`, { url, technique, key }),
  // upload local files (each with a relative path) -> catalog + an upload:// url for follow-up calls
  upload: async (files: { file: File; path: string }[]): Promise<CatalogResult & { url: string }> => {
    const form = new FormData();
    for (const { file, path } of files) form.append("files", file, path);
    const res = await fetch(`${BASE}/api/upload`, { method: "POST", body: form });
    if (!res.ok) {
      const b = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(b.detail ?? res.statusText);
    }
    return res.json();
  },
};

// Direct download URL for converting a dataset to a standard format (csdf | h5 | jcamp | …).
export function convertUrl(url: string, name: string, technique: string, fmt: string): string {
  return `${BASE}/api/convert?url=${q(url)}&name=${q(name)}&technique=${q(technique)}&fmt=${fmt}`;
}

// Enriched export: POST the user-edited metadata so it's embedded in the converted file. Returns the
// file as a Blob (triggered as a download by the caller).
export async function exportEnriched(payload: {
  url: string;
  name: string;
  technique: string;
  fmt: string;
  metadata: unknown;
}): Promise<Blob> {
  const res = await fetch(`${BASE}/api/convert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const b = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(b.detail ?? res.statusText);
  }
  return res.blob();
}

// Absolute URL for an <audio> element to stream a dataset's .wav (the backend returns a relative path).
export function audioSrc(ds: DatasetData): string | null {
  return ds.audio_url ? `${BASE}${ds.audio_url}` : null;
}
