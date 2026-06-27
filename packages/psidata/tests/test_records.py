from __future__ import annotations

from psidata.sources import FileRef, build_entry, build_records, classify_format
from psidata.sources.records import (
    BINARY_ORIGINAL,
    DATA,
    IMAGE,
    SIDECAR,
    SPREADSHEET,
)


def _records(paths: list[str]):
    entries = [build_entry(FileRef(path=p, size=1)) for p in paths]
    return build_records(entries)


# --- classification ---------------------------------------------------------------------------
def test_classify_format_roles():
    assert classify_format("x.csv").role == DATA
    assert classify_format("x.dpt").role == DATA
    assert classify_format("x.tri").role == BINARY_ORIGINAL
    assert classify_format("x.xls").role == SPREADSHEET
    assert classify_format("sample_1.0").role == BINARY_ORIGINAL  # Bruker OPUS block file
    assert classify_format("photo.jpg").role == IMAGE
    sidecar = classify_format("run_spec.txt")
    assert sidecar.role == SIDECAR and not sidecar.is_data


# --- DSC: one dataset saved as csv + tri + xls ------------------------------------------------
def test_dsc_multiformat_collapses_to_one_record():
    recs = _records([
        "DSC/2026_05_26_Acetaminophen_DSC.csv",
        "DSC/2026_05_26_Acetaminophen_DSC.tri",
        "DSC/2026_05_26_Acetaminophen_DSC.xls",
    ])
    assert len(recs) == 1
    r = recs[0]
    assert r.technique == "DSC"
    assert r.formats == [".csv", ".tri", ".xls"]
    assert r.supported and r.primary.ext == ".csv"        # text data is the primary
    roles = {v.ext: v.info.role for v in r.variants}
    assert roles[".tri"] == BINARY_ORIGINAL               # Trios binary original
    assert roles[".xls"] == SPREADSHEET
    # .csv (DSC reader) and .xls (generic spreadsheet reader) are both parseable; .csv stays primary
    assert {v.ext for v in r.parseable_variants} == {".csv", ".xls"}


def test_dsc_txt_variant_is_primary_when_no_csv():
    r = _records(["DSC/run.txt", "DSC/run.xls"])[0]
    assert r.primary.ext == ".txt"


# --- Raman: csv (data) + _spec.txt (sidecar, NOT data) ----------------------------------------
def test_raman_spec_txt_grouped_and_flagged_as_sidecar():
    recs = _records([
        "Raman/2022_CBD_532nm_977wn_iDus_30s.csv",
        "Raman/2022_CBD_532nm_977wn_iDus_30s_spec.txt",
    ])
    assert len(recs) == 1                                  # grouped despite the _spec suffix
    r = recs[0]
    assert r.primary.ext == ".csv"
    assert len(r.sidecars) == 1 and r.sidecars[0].ext == ".txt"
    sidecar = r.sidecars[0]
    assert not sidecar.info.is_data                        # the _spec.txt holds params, not data
    assert not sidecar.parseable                           # must NOT be read as a Raman spectrum


# --- FTIR: ascii export + native binary -------------------------------------------------------
def test_ftir_dpt_plus_opus_binary():
    r = _records(["FTIR/2023_silk_1.dpt", "FTIR/2023_silk_1.0"])[0]
    assert r.primary.ext == ".dpt"
    assert any(v.info.role == BINARY_ORIGINAL for v in r.variants)


# --- image-only records are not datasets ------------------------------------------------------
def test_image_only_is_not_a_data_record():
    r = _records(["FTIR/2023_sample_photo.jpg"])[0]
    assert not r.is_data_record
    assert r.primary is None


def test_record_summary_shape():
    r = _records(["DSC/2026_05_26_Acetaminophen_DSC.csv", "DSC/2026_05_26_Acetaminophen_DSC.tri"])[0]
    s = r.summary()
    assert s["technique"] == "DSC"
    assert s["primary"] == ".csv"
    assert set(s["formats"]) == {".csv", ".tri"}
    assert s["date"] == "2026-05-26"


# --- technique normalization: "IR" and "FTIR" folders are the same technique ------------------
def test_ir_folder_normalizes_to_ftir():
    from psidata.sources import canonical_technique

    ir = build_entry(FileRef(path="IR/2026_01_01_silk_ATR.dpt", size=1))
    ftir = build_entry(FileRef(path="FTIR/2026_01_01_silk_ATR.dpt", size=1))
    assert ir.technique == "FTIR" == ftir.technique
    assert ir.supported  # the FTIR reader still matches the normalized folder
    assert canonical_technique("UV_Vis") == "UV-Vis"
    assert canonical_technique("NMR") == "NMR"  # unmapped folders pass through unchanged


def test_ir_and_ftir_records_share_one_technique_group():
    recs = _records([
        "IR/2026_01_01_silk_ATR.dpt",
        "FTIR/2026_02_02_pdms_ATR.dpt",
    ])
    assert {r.technique for r in recs} == {"FTIR"}


def test_record_uid_unique_across_subfolders():
    # the same base name in different sub-folders (e.g. MD runs) must yield distinct records + uids
    entries = [build_entry(FileRef(path=f"Computational/run{i}/min.pdb", size=1)) for i in range(3)]
    recs = build_records(entries)
    assert len(recs) == 3
    assert len({r.uid for r in recs}) == 3
    assert all(r.key == "min" for r in recs)  # the display key is still the base name
