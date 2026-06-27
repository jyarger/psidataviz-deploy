from __future__ import annotations

import pytest

from psidata_backend import molecule


def test_smiles_to_molblock_embeds_3d():
    mb = molecule.smiles_to_molblock("c1ccccc1C=O")  # benzaldehyde
    assert "V2000" in mb
    assert len(mb.splitlines()) > 12  # header + atoms + bonds


def test_molecule_payload_q_detects_smiles_offline():
    payload = molecule.molecule_payload(q="CCO")  # ethanol — valid SMILES, no network needed
    assert payload["smiles"] == "CCO"
    assert "V2000" in payload["molblock"]
    assert payload["query"] == "CCO"


def test_invalid_smiles_raises():
    with pytest.raises(ValueError):
        molecule.smiles_to_molblock("this-is-not-smiles)((")


def test_mol_svg_renders_for_smiles():
    svg = molecule.mol_svg("c1ccccc1C=O")  # benzaldehyde
    assert svg and "<svg" in svg


def test_payload_includes_svg_for_smiles_offline():
    payload = molecule.molecule_payload(q="CCO")  # ethanol — no network needed
    assert payload["svg"] and "<svg" in payload["svg"]
    assert payload["cas"] is None  # no CID without a name lookup, so no CAS
