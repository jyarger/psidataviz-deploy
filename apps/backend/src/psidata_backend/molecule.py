"""Resolve a SMILES string or a compound name to a 3D structure for the molecular viewer.

SMILES are embedded into 3D coordinates with RDKit; names (common or IUPAC) are first resolved to a
SMILES via the public PubChem PUG REST API. The result is an MDL mol block that 3Dmol.js renders.
"""

from __future__ import annotations

import re
import urllib.parse

import httpx

_PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


def smiles_to_molblock(smiles: str) -> str:
    """Embed a SMILES string into an optimized 3D MDL mol block (falls back to 2D if embedding fails)."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=0xF00D) == 0:
        try:
            AllChem.MMFFOptimizeMolecule(mol)
        except Exception:  # noqa: BLE001  optimization is best-effort
            pass
    else:
        AllChem.Compute2DCoords(mol)  # embedding failed (e.g. odd valences) — show a flat layout
    return Chem.MolToMolBlock(mol)


def resolve_name(name: str) -> dict:
    """Resolve a compound name (common or IUPAC) to SMILES + canonical info via PubChem."""
    quoted = urllib.parse.quote(name.strip())
    url = f"{_PUBCHEM}/compound/name/{quoted}/property/CanonicalSMILES,IUPACName,MolecularFormula/JSON"
    resp = httpx.get(url, timeout=12.0, follow_redirects=True)
    if resp.status_code == 404:
        raise ValueError(f"No compound found for {name!r}")
    resp.raise_for_status()
    props = resp.json()["PropertyTable"]["Properties"][0]
    smiles = next((v for k, v in props.items() if "SMILES" in k), None)
    if not smiles:
        raise ValueError(f"PubChem returned no SMILES for {name!r}")
    return {"smiles": smiles, "iupac": props.get("IUPACName"),
            "formula": props.get("MolecularFormula"), "cid": props.get("CID")}


def cas_for_cid(cid: int) -> str | None:
    """Find a CAS registry number among a PubChem compound's synonyms (best-effort)."""
    try:
        resp = httpx.get(f"{_PUBCHEM}/compound/cid/{cid}/synonyms/JSON", timeout=10.0,
                         follow_redirects=True)
        if resp.status_code != 200:
            return None
        syns = resp.json()["InformationList"]["Information"][0].get("Synonym", [])
        return next((s for s in syns if _CAS_RE.match(s)), None)
    except Exception:  # noqa: BLE001  CAS is a nice-to-have; never fail the lookup over it
        return None


def mol_svg(smiles: str, size: int = 280) -> str | None:
    """A 2D structure depiction (SVG) for confirming chemical identity."""
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        AllChem.Compute2DCoords(mol)
        drawer = rdMolDraw2D.MolDraw2DSVG(size, int(size * 0.72))
        drawer.drawOptions().clearBackground = False
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception:  # noqa: BLE001  depiction is optional
        return None


def molecule_payload(*, smiles: str | None = None, name: str | None = None,
                     q: str | None = None) -> dict:
    """Build the viewer payload from a SMILES string, a compound name, or a free-text ``q`` that is tried
    as SMILES first (offline) and otherwise resolved as a name via PubChem."""
    from rdkit import Chem

    resolved: dict = {}
    if q:
        q = q.strip()
        if Chem.MolFromSmiles(q) is not None:
            smiles = q
        else:
            name = q
    if name and not smiles:
        resolved = resolve_name(name)
        smiles = resolved["smiles"]
    if not smiles:
        raise ValueError("provide either a SMILES string or a compound name")
    cid = resolved.get("cid")
    return {
        "molblock": smiles_to_molblock(smiles),
        "smiles": smiles,
        "query": q or name or smiles,
        "iupac": resolved.get("iupac"),
        "formula": resolved.get("formula"),
        "cid": cid,
        "cas": cas_for_cid(cid) if cid else None,
        "svg": mol_svg(smiles),
    }
