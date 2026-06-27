import type { DatasetData } from "./api";

export type TagCategory = "condition" | "instrument" | "chemical";
export interface Tag {
  category: TagCategory;
  value: string;
}
export interface EditableMetadata {
  sample_name: string;
  formula: string;
  smiles: string;
  cas: string;
  instrument: string;
  operator: string;
  date: string;
  time: string;
  solvent: string;
  temperature: string;
  pressure: string;
  notes: string;
  tags: Tag[];
}

const firstOf = (m: Record<string, unknown>, ...keys: string[]): string => {
  for (const k of keys) if (m[k] != null) return String(m[k]);
  return "";
};

// Pre-fill the editable metadata from whatever the reader recovered (the universal metadata + the
// technique-specific extras surfaced at the top level, e.g. solvent / temperature_k).
export function deriveMetadata(ds: DatasetData): EditableMetadata {
  const m = ds.metadata;
  return {
    sample_name: firstOf(m, "sample_name") || ds.filename,
    formula: firstOf(m, "formula", "molecular_formula"),
    smiles: firstOf(m, "smiles"),
    cas: firstOf(m, "cas", "cas_rn", "cas_registry_no"),
    instrument: firstOf(m, "instrument", "spectrometer"),
    operator: firstOf(m, "operator", "owner"),
    date: firstOf(m, "date"),
    time: firstOf(m, "time"),
    solvent: firstOf(m, "solvent"),
    temperature: firstOf(m, "temperature", "temperature_k"),
    pressure: firstOf(m, "pressure"),
    notes: firstOf(m, "notes"),
    tags: [],
  };
}
