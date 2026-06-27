// Tokens that mark the end of the compound part of a dataset name (techniques, instruments, conditions,
// descriptors, common solvents).
const STOP = new Set([
  "ms", "sims", "dsc", "nmr", "ir", "ftir", "raman", "xrd", "pxrd", "saxs", "waxs", "hplc", "dad",
  "tga", "uv", "vis", "uvvis", "cd", "dielectric", "brillouin", "acoustic", "ea", "sem", "tem",
  "data", "spectrum", "sample", "raw", "pos", "neg", "blank", "std", "opt", "freq", "scan", "edit",
  "meoh", "etoh", "h2o", "thf", "dcm", "dmso", "acn", "mecn", "si",
  "xtal", "crystal", "cryst", "powder", "film", "soln", "solution", "neat", "bulk", "thin", "depol",
  "pol", "run", "test", "rep", "deg", "rt",
  "dft", "b3lyp", "hf", "mp2", "ccsd", "am1", "pm3", "wb97xd", "m06", "gaussian", "gaussian16",
  "orca", "psi4", "sp", "scf", "pcsseg", "conformer", "conformers", "tablet",
]);

// Best-effort compound guess from a dataset name: the leading word tokens up to the first technique /
// instrument / condition token. Returns "" when nothing looks like a real compound.
export function guessCompound(raw: string): string {
  let s = raw.replace(/\.[a-z0-9]+$/i, ""); // strip an extension
  s = s.replace(/^\d{4}[-_]\d{2}[-_]\d{2}[-_]?/, ""); // strip a leading ISO date
  const out: string[] = [];
  for (const t of s.split(/[_\-\s.]+/).filter(Boolean)) {
    const low = t.toLowerCase();
    if (STOP.has(low)) break;
    if (/\d/.test(t)) break; // a digit means a setting/date/formula (532nm, 1mW, FeCl3) — stop here
    if (/(nm|mw|mg|ml|mm|cm|hz|mhz|kv|um|kev)$/i.test(low)) break; // a unit suffix
    out.push(t);
  }
  if (!out.some((t) => /[a-zA-Z]{3,}/.test(t))) return ""; // need at least one real word
  return out.join(" ");
}
