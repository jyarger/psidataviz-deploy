from __future__ import annotations

import io
import zipfile

import pytest

from psidata import ArchiveError, read_zip, zip_datasets


def _zip(files: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_read_zip_of_text_data_file(dsc_txt):
    content = _zip({
        "__MACOSX/._x.txt": "junk",                    # macOS fork — must be ignored
        "2023_06_14_Indium_wire_std.txt": dsc_txt,
    })
    ds = read_zip("2023_06_14_Indium_wire_std.txt.zip", content)
    assert ds.technique == "DSC"
    assert len(ds.signals) == 2


def test_read_zip_passes_technique_hint(raman_csv):
    content = _zip({"2022_CBD_977wn.csv": raman_csv})
    ds = read_zip("2022_CBD_977wn.csv.zip", content, technique_hint="Raman")
    assert ds.technique == "Raman"


def test_bruker_directory_archive_reports_clearly():
    content = _zip({"expt/1/fid": b"\x00\x01\x02\x03", "expt/1/acqus": "##TITLE= acqus\n"})
    with pytest.raises(ArchiveError, match="Bruker"):
        read_zip("dataset.zip", content)


def test_empty_or_unknown_archive_raises():
    with pytest.raises(ArchiveError):
        read_zip("empty.zip", _zip({}))
    with pytest.raises(ArchiveError, match="no recognized data"):
        read_zip("imgs.zip", _zip({"a.png": b"\x89PNG"}))


def test_read_nested_zip(dsc_txt):
    # a zip whose only useful content is another zip (a dataset bundled inside a bundle)
    inner = _zip({"2023_06_14_Indium_wire_std.txt": dsc_txt})
    outer = _zip({"bundle/inner.zip": inner, "bundle/notes.md": "# readme"})
    ds = read_zip("bundle.zip", outer)
    assert ds.technique == "DSC" and len(ds.signals) == 2


def test_zip_picks_parseable_member_among_junk(dsc_txt):
    # the registry (not a hard-coded extension list) chooses the data file amid previews/notes
    content = _zip({"preview.png": b"\x89PNG\r\n", "readme.md": "# notes", "run.txt": dsc_txt})
    ds = read_zip("mixed.zip", content)
    assert ds.technique == "DSC"


def test_zip_datasets_lists_several_and_loads_member(dsc_txt):
    content = _zip({
        "2023_runA_DSC.txt": dsc_txt,
        "2023_runB_DSC.txt": dsc_txt,
        "notes.md": "# just notes",          # not a dataset -> filtered out
    })
    datasets = zip_datasets("bundle.zip", content, technique_hint="DSC")
    assert sorted(d["key"] for d in datasets) == ["2023_runA_DSC", "2023_runB_DSC"]
    ds = read_zip("bundle.zip", content, technique_hint="DSC", member="2023_runB_DSC.txt")
    assert ds.technique == "DSC" and len(ds.signals) == 2


def test_zip_datasets_collapses_one_dataset_many_formats(dsc_txt):
    # several formats of the SAME measurement (one base name) -> a single dataset
    content = _zip({"run_DSC.txt": dsc_txt, "run_DSC.csv": dsc_txt})
    datasets = zip_datasets("one.zip", content, technique_hint="DSC")
    assert len(datasets) == 1
    assert set(datasets[0]["formats"]) == {"txt", "csv"}


def test_read_spinsolve_zip():
    content = _zip({
        "NMR_x/spectrum_processed.csv": "Frequency(ppm),Intensity\n10.0,1.0\n9.0,2.0\n8.0,1.5\n",
        "NMR_x/acqu.par": 'Sample = "TestSample"\nSolvent = "CDCl3"\nb1Freq = 80.0\n',
        "NMR_x/data.jpg": b"\x89PNG",
    })
    ds = read_zip("NMR_Acac_SpinSolve80.zip", content, technique_hint="NMR")
    assert ds.technique == "NMR" and ds.source.reader == "nmr_spinsolve_zip"
    sig = ds.signals[0]
    assert sig.x.label == "Chemical shift" and sig.x.unit == "ppm"
    assert list(sig.frame["Chemical shift"]) == [10.0, 9.0, 8.0]
    assert list(sig.frame["Intensity"]) == [1.0, 2.0, 1.5]
    assert ds.metadata.sample_name == "TestSample"
    assert ds.metadata.solvent == "CDCl3"
    assert ds.metadata.frequency_mhz == 80.0


def test_read_bruker_processed_zip():
    import numpy as np

    one_r = np.array([100, 200, 50, 10], dtype="<i4").tobytes()
    procs = ("##$SI= 4\n##$SW_p= 400.0\n##$SF= 100.0\n##$OFFSET= 10.0\n"
             "##$NC_proc= 0\n##$BYTORDP= 0\n")
    content = _zip({
        "expt/1/pdata/1/1r": one_r,
        "expt/1/pdata/1/procs": procs,
        "expt/1/pdata/1/title": "MySample\n",
        "expt/1/acqus": "##$SFO1= 100.0\n",
    })
    ds = read_zip("NMR_AcAc_Bruker400.zip", content, technique_hint="NMR")
    assert ds.technique == "NMR" and ds.source.reader == "nmr_bruker_zip"
    sig = ds.signals[0]
    assert sig.npoints == 4
    # ppm: point 0 = OFFSET (10), step SW_p/SF/SI = 400/100/4 = 1 -> [10, 9, 8, 7]
    assert list(sig.frame["Chemical shift"]) == [10.0, 9.0, 8.0, 7.0]
    assert list(sig.frame["Intensity"]) == [100.0, 200.0, 50.0, 10.0]
    assert ds.metadata.sample_name == "MySample"
    assert ds.metadata.frequency_mhz == 100.0


def _bruker_procs(si: int, **extra: str) -> bytes:
    text = (f"##$SI= {si}\n##$BYTORDP= 0\n##$NC_proc= 0\n##$SW_p= 4000\n##$SF= 400\n"
            f"##$OFFSET= 10\n##$XDIM= {si}\n")
    for k, v in extra.items():
        text += f"##${k}= {v}\n"
    return text.encode()


def _acqus(pulprog: str, nuc1: str, nuc2: str = "off") -> bytes:
    return f"##$PULPROG= <{pulprog}>\n##$NUC1= <{nuc1}>\n##$NUC2= <{nuc2}>\n".encode()


def test_multi_experiment_bruker_zip_lists_each_experiment():
    import numpy as np

    content = _zip({
        # experiment 1 — 1H 1D
        "CBD/1/acqus": _acqus("zg30", "1H"),
        "CBD/1/pdata/1/procs": _bruker_procs(4),
        "CBD/1/pdata/1/1r": np.array([1, 2, 3, 4], dtype="<i4").tobytes(),
        "CBD/1/pdata/1/title": b"CBD 1H",
        # experiment 2 — homonuclear COSY 2D (NUC2 off -> F1 is also 1H)
        "CBD/2/acqus": _acqus("cosygpmfphpp", "1H", "off"),
        "CBD/2/pdata/1/procs": _bruker_procs(2),
        "CBD/2/pdata/1/proc2s": _bruker_procs(2),
        "CBD/2/pdata/1/2rr": np.array([1, 2, 3, 4], dtype="<i4").tobytes(),
    })

    datasets = zip_datasets("NMR_CBD_Bruker400.zip", content, technique_hint="NMR")
    assert [d["key"] for d in datasets] == ["1H", "COSY"]  # one entry per numbered experiment

    one = read_zip("NMR_CBD_Bruker400.zip", content, technique_hint="NMR", member=datasets[0]["member"])
    assert one.signals and one.signals[0].npoints == 4 and not one.images

    two = read_zip("NMR_CBD_Bruker400.zip", content, technique_hint="NMR", member=datasets[1]["member"])
    assert not two.signals and two.images and two.images[0].kind == "nmr2d"
    assert two.images[0].data.shape == (2, 2)
    assert two.images[0].y.label.startswith("1H")  # homonuclear: indirect dim is 1H, not "off"


def test_single_experiment_bruker_zip_stays_one_dataset():
    import numpy as np

    content = _zip({
        "AcAc/1/acqus": _acqus("zg30", "1H"),
        "AcAc/1/pdata/1/procs": _bruker_procs(4),
        "AcAc/1/pdata/1/1r": np.array([5, 6, 7, 8], dtype="<i4").tobytes(),
    })
    datasets = zip_datasets("NMR_AcAc.zip", content)
    assert len(datasets) == 1 and datasets[0]["member"] is None  # no member selector for a single experiment
    ds = read_zip("NMR_AcAc.zip", content, technique_hint="NMR")
    assert ds.signals and ds.signals[0].npoints == 4
