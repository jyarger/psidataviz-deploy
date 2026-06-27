"""Tests for tarball (.tar.bz2) archive support and the Agilent ChemStation DAD reader."""
from __future__ import annotations

import bz2
import io
import tarfile

from psidata import Candidate, archive_datasets, is_archive, read, read_archive


def _tar_bz2(files: dict[str, bytes]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return bz2.compress(raw.getvalue())


def _dad_csv() -> bytes:
    rows = [",210,254,280"]  # first cell empty, then wavelengths
    rows += [f"{i * 0.1},{i * 1.0},{i * 2.0},{i * 0.5}" for i in range(12)]
    return "\n".join(rows).encode("utf-16")  # DAD exports are UTF-16


def test_is_archive_recognizes_tarballs():
    assert is_archive("x.zip") and is_archive("x.tar.bz2") and is_archive("x.tgz")
    assert not is_archive("x.csv") and not is_archive("x.txt")


def test_read_tarball_of_dad_runs():
    content = _tar_bz2({"run/ba_1.D/DAD1.CSV": _dad_csv(), "run/blank.D/DAD1.CSV": _dad_csv()})
    members = archive_datasets("benzaldehyde.tar.bz2", content, technique_hint="HPLC")
    assert len(members) == 2  # two .D runs listed as distinct datasets
    ds = read_archive("benzaldehyde.tar.bz2", content, technique_hint="HPLC",
                      member=members[0]["member"])
    assert ds.technique == "HPLC" and ds.source.reader == "agilent_dad"
    assert ds.metadata.sample_name in ("ba_1", "blank")  # run name from the .D folder


def test_agilent_dad_reads_wavelength_chromatograms():
    ds = read(Candidate(filename="DAD1.CSV", content=_dad_csv(), uri="run/ba_1.D/DAD1.CSV",
                        technique_hint="HPLC"))
    assert ds.source.reader == "agilent_dad"
    assert ds.metadata.sample_name == "ba_1"
    labels = {s.segment for s in ds.signals}
    assert "254 nm" in labels and "280 nm" in labels
    s = ds.signals[0]
    assert (s.x.label, s.x.unit) == ("Retention time", "min")
    assert (s.y.label, s.y.unit) == ("Absorbance", "mAU")
