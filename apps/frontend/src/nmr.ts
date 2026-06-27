import type { DatasetData } from "./api";

// Pretty-print a nucleus token ("1H", "13C", "19F") with proper superscript mass numbers.
const SUP: Record<string, string> = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
  "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };
export function fmtNuc(raw: string): string {
  const m = /^\s*(\d+)\s*([A-Za-z]+)\s*$/.exec(raw || "");
  if (!m) return raw || "NMR";
  const mass = [...m[1]].map((d) => SUP[d] ?? d).join("");
  const el = m[2][0].toUpperCase() + m[2].slice(1).toLowerCase();
  return `${mass}${el}`;
}

// "13C F1" / "1H F2" -> "13C" / "1H"
export function nucOf(axisLabel: string): string {
  return (axisLabel || "").replace(/\s*F[12]\s*$/i, "").trim() || "NMR";
}

// 1D nucleus display order (common observe nuclei first)
const NUC_ORDER = ["1H", "19F", "31P", "13C", "11B", "15N", "29SI", "2H"];
function nucRank(n: string): number {
  const i = NUC_ORDER.indexOf((n || "").toUpperCase());
  return i < 0 ? NUC_ORDER.length : i;
}

const EXPERIMENTS: [RegExp, string][] = [
  [/hsqc/i, "HSQC"], [/hmbc/i, "HMBC"], [/h2bc/i, "H2BC"], [/hmqc/i, "HMQC"],
  [/cosy/i, "COSY"], [/noesy/i, "NOESY"], [/roesy/i, "ROESY"], [/tocsy/i, "TOCSY"],
  [/jres|j-?res/i, "J-res"], [/dept\s*135|dept135/i, "DEPT-135"], [/dept\s*90|dept90/i, "DEPT-90"],
  [/dept/i, "DEPT"], [/\bapt\b/i, "APT"],
];

// Short experiment name (HSQC / COSY / DEPT-135 …) from the pulse program / experiment / filename.
export function expName(ds: DatasetData): string {
  const hay = [ds.metadata.pulse_sequence, ds.metadata.experiment, ds.filename]
    .filter(Boolean).join(" ");
  for (const [re, name] of EXPERIMENTS) if (re.test(hay)) return name;
  return (ds.metadata.experiment as string) || ds.filename;
}

export interface NMRTab {
  key: string;
  label: string; // e.g. "¹H", "¹H–¹³C"
  is2d: boolean;
  datasets: DatasetData[];
  order: number;
}

// Group a compound's NMR datasets into NMRium-style tabs: one per nucleus (1D) or nucleus pair (2D).
export function categorizeNMR(datasets: DatasetData[]): NMRTab[] {
  const groups = new Map<string, NMRTab>();
  for (const ds of datasets) {
    const img = ds.images?.find((i) => i.kind === "nmr2d");
    let key: string, label: string, is2d: boolean, order: number;
    if (img) {
      const direct = nucOf(img.x.label); // F2 = directly observed
      const indirect = nucOf(img.y.label); // F1
      label = `${fmtNuc(direct)}–${fmtNuc(indirect)}`;
      key = `2d:${direct}:${indirect}`;
      is2d = true;
      order = 100 + nucRank(direct) * 10 + nucRank(indirect);
    } else {
      const nuc = (ds.metadata.nucleus as string) || "NMR";
      label = fmtNuc(nuc);
      key = `1d:${nuc.toUpperCase()}`;
      is2d = false;
      order = nucRank(nuc);
    }
    const existing = groups.get(key);
    if (existing) existing.datasets.push(ds);
    else groups.set(key, { key, label, is2d, datasets: [ds], order });
  }
  return [...groups.values()].sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
}
