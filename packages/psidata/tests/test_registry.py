from __future__ import annotations

import pytest

from psidata import Candidate, UnknownFormatError, detect, get_readers, read, score_readers


def test_dsc_reader_is_registered():
    names = {r.name for r in get_readers()}
    assert "dsc_trios" in names


def test_detect_dsc_by_content(dsc_txt):
    cand = Candidate(filename="2023_06_14_Indium_wire_std.txt", text=dsc_txt)
    reader = detect(cand)
    assert reader is not None
    assert reader.technique == "DSC"


def test_sniff_confidence_high_for_dsc(dsc_txt):
    cand = Candidate(filename="run.txt", text=dsc_txt)
    top_reader, top_score = score_readers(cand)[0]
    assert top_reader.name == "dsc_trios"
    assert top_score >= 0.8


def test_unknown_content_returns_none():
    cand = Candidate(filename="notes.txt", text="just some unrelated text\nwith no markers\n")
    assert detect(cand) is None
    with pytest.raises(UnknownFormatError):
        read(cand)
