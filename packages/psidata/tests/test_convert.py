from __future__ import annotations

import json
from pathlib import Path

from psidata import Candidate, convert, read
from psidata.convert import to_csdm, to_csv, to_csv_zip, to_feather, to_hdf5, to_parquet, to_zarr


def _dataset(dsc_txt: str):
    return read(Candidate(filename="2026_01_01_run.txt", text=dsc_txt))


def test_to_csdm_json_structure(dsc_txt):
    doc = json.loads(to_csdm(_dataset(dsc_txt)))["csdm"]
    assert doc["version"] == "1.0"
    assert len(doc["dimensions"]) == 1
    # DSC temperature is not evenly spaced -> monotonic dimension
    assert doc["dimensions"][0]["type"] == "monotonic"
    dv = doc["dependent_variables"]
    assert len(dv) >= 1
    assert dv[0]["numeric_type"] == "float64"
    assert len(dv[0]["components"][0]) == len(doc["dimensions"][0]["coordinates"])


def test_to_csdm_linear_dimension():
    # an evenly spaced abscissa -> linear dimension
    nmr = (
        "##TITLE=t\n##JCAMP-DX=5.01\n##DATA TYPE= NMR SPECTRUM\n##.OBSERVE NUCLEUS=1H\n"
        "##XUNITS=PPM\n##XYDATA=(XY..XY)\n10 1\n9 2\n8 5\n7 2\n6 1\n##END=\n"
    )
    doc = json.loads(to_csdm(read(Candidate(filename="x.jdx", text=nmr))))["csdm"]
    assert doc["dimensions"][0]["type"] == "linear"
    assert doc["dimensions"][0]["count"] == 5


def test_to_hdf5_roundtrip(dsc_txt, tmp_path):
    import h5py

    path = to_hdf5(_dataset(dsc_txt), tmp_path / "out.h5")
    with h5py.File(path) as f:
        assert f.attrs["technique"] == "DSC"
        group = f["signals/signal_0"]
        assert group.attrs["x_label"] == "Temperature"
        assert len(group["x"]) == len(group["y"]) > 0


def test_to_zarr_roundtrip(dsc_txt, tmp_path):
    import zarr

    path = to_zarr(_dataset(dsc_txt), str(tmp_path / "out.zarr"))
    root = zarr.open_group(path, mode="r")
    assert root.attrs["technique"] == "DSC"
    group = root["signals/signal_0"]
    assert group.attrs["y_label"].startswith("Heat Flow")
    assert group["x"].shape[0] > 0


def test_convert_dispatch_by_suffix(dsc_txt, tmp_path):
    out = convert(_dataset(dsc_txt), tmp_path / "a.csdf")
    assert out.endswith(".csdf")
    assert json.loads(Path(out).read_text())["csdm"]["version"] == "1.0"


def test_to_csv_parquet_feather_tidy(dsc_txt, tmp_path):
    import pandas as pd

    ds = _dataset(dsc_txt)
    csv_df = pd.read_csv(to_csv(ds, tmp_path / "a.csv"))
    assert "signal" in csv_df.columns and len(csv_df) > 0
    assert pd.read_parquet(to_parquet(ds, tmp_path / "a.parquet")).shape == csv_df.shape
    assert pd.read_feather(to_feather(ds, tmp_path / "a.feather")).shape == csv_df.shape


def test_to_csv_zip_one_per_signal(dsc_txt, tmp_path):
    import zipfile

    ds = _dataset(dsc_txt)  # DSC indium -> 2 thermal segments
    with zipfile.ZipFile(to_csv_zip(ds, tmp_path / "a.zip")) as zf:
        names = zf.namelist()
    assert len(names) == len(ds.signals) == 2
    assert all(n.endswith(".csv") for n in names)


def test_convert_dispatch_tabular_formats(dsc_txt, tmp_path):
    ds = _dataset(dsc_txt)
    for ext in ("csv", "parquet", "feather", "zip"):
        assert convert(ds, tmp_path / f"x.{ext}").endswith(ext)


def test_to_jcamp_embeds_metadata_headers(tmp_path):
    import pandas as pd

    from psidata.convert import to_jcamp
    from psidata.model import Axis, Dataset, Metadata, Signal, SourceInfo

    md = Metadata(sample_name="Aspirin")
    md.smiles = "CC(=O)Oc1ccccc1C(=O)O"
    md.cas = "50-78-2"
    md.formula = "C9H8O4"
    md.tags = [{"category": "condition", "value": "298 K"}]
    sig = Signal(name="s", x=Axis(label="Wavenumber", unit="cm-1"), y=Axis(label="A", unit="a.u."),
                 frame=pd.DataFrame({"Wavenumber": [4000.0, 2000.0], "A": [0.1, 0.9]}))
    ds = Dataset(technique="FTIR", source=SourceInfo(filename="x.dpt"), metadata=md, signals=[sig])
    text = open(to_jcamp(ds, tmp_path / "out.jdx")).read()
    assert "##TITLE=Aspirin" in text
    assert "##DATA TYPE=INFRARED SPECTRUM" in text
    assert "##SMILES=CC(=O)Oc1ccccc1C(=O)O" in text
    assert "##CAS REGISTRY NO=50-78-2" in text
    assert "##MOLECULAR FORMULA=C9H8O4" in text
    assert "##$TAG CONDITION=298 K" in text
    assert text.rstrip().endswith("##END=")
