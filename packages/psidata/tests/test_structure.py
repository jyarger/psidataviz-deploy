from __future__ import annotations

import numpy as np

from psidata import Candidate, read
from psidata.readers.comp_log import _structure_from_ccdata
from psidata.readers.structure_file import StructureFileReader, _count_atoms

WATER_XYZ = "3\nwater\nO   0.000  0.000  0.000\nH   0.757  0.586  0.000\nH  -0.757  0.586  0.000\n"


def test_structure_file_reads_xyz():
    ds = read(Candidate(filename="water.xyz", text=WATER_XYZ))
    assert ds.structure is not None
    assert ds.structure.fmt == "xyz"
    assert ds.structure.n_atoms == 3
    assert ds.signals == []  # structure-only dataset
    assert ds.summary()["structure"] == {"format": "xyz", "n_atoms": 3}


def test_structure_sniff():
    r = StructureFileReader()
    assert r.sniff(Candidate(filename="m.xyz", text=WATER_XYZ)) == 0.8
    assert r.sniff(Candidate(filename="m.xyz", text="not a count\n")) == 0.0
    assert r.sniff(Candidate(filename="m.csv", text=WATER_XYZ)) == 0.0  # wrong extension


def test_count_atoms_molfile():
    mol = "name\n  app\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\nM  END\n"
    assert _count_atoms(".mol", mol) == 3


def test_structure_from_ccdata():
    class FakeCC:
        atomcoords = [np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.96]])]
        atomnos = np.array([8, 1])

    s = _structure_from_ccdata(FakeCC(), "OH")
    assert s.fmt == "xyz" and s.n_atoms == 2
    lines = s.data.splitlines()
    assert lines[0] == "2"
    assert lines[2].startswith("O") and lines[3].startswith("H")


def test_comp_log_modes_from_ccdata():
    from psidata.readers.comp_log import _modes_from_ccdata

    class FakeCC:
        vibfreqs = [107.4, 1159.1]
        vibdisps = [[[0.0, 0.0, -0.23], [0.0, 0.0, 0.10]], [[0.10, 0.0, 0.0], [0.0, 0.10, 0.0]]]
        vibirs = [6.48, 298.99]
        vibramans = [0.05, 1.2]

    modes = _modes_from_ccdata(FakeCC())
    assert len(modes) == 2
    assert modes[1].freq == 1159.1 and modes[1].ir == 298.99
    assert len(modes[0].disps) == 2 and modes[0].disps[0] == (0.0, 0.0, -0.23)


def test_comp_input_reads_gaussian_gjf_geometry():
    gjf = (
        "%mem=8GB\n%chk=x.chk\n#p opt freq b3lyp/6-31g(d)\n\n"
        "r134a title\n\n0 1\n"
        " C   -1.501439    1.410611    1.456949\n"
        " H   -1.182454    2.431922    1.448389\n"
        " C   -0.305047    0.496427    1.133662\n"
        "\n 1 2 1.0 3 1.0\n 2\n"  # connectivity lines must be ignored
    )
    ds = read(Candidate(filename="r134a_Gaussian16.gjf",
                        content=gjf.encode(), technique_hint="Computational"))
    assert ds.source.reader == "comp_input"
    assert ds.signals == [] and ds.structure is not None
    assert ds.structure.fmt == "xyz" and ds.structure.n_atoms == 3
    assert ds.structure.data.splitlines()[2].startswith("C")


def test_comp_input_skips_orca_external_xyzfile():
    from psidata.readers.comp_input import CompInputReader

    inp = "! B3LYP def2-SVP Opt\n%pal nprocs 4 end\n* xyzfile 0 1 geom.xyz\n"
    # no inline coordinates -> not claimed (the geometry is in the referenced .xyz)
    assert CompInputReader().sniff(Candidate(filename="x.inp", text=inp)) == 0.0
