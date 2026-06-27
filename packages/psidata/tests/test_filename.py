from __future__ import annotations

from datetime import date

from psidata.filename import parse_filename


def test_parses_leading_date_and_description():
    p = parse_filename("2023_06_14_Indium_wire_std.txt")
    assert p.date == date(2023, 6, 14)
    assert p.description == "Indium wire std"
    assert p.tokens == ["Indium", "wire", "std"]
    assert p.has_date


def test_strips_directory_and_extension():
    p = parse_filename("DSC/2023_04_21_CBD_Xtal_Powder.xls")
    assert p.stem == "2023_04_21_CBD_Xtal_Powder"
    assert p.date == date(2023, 4, 21)


def test_no_date_falls_back_to_stem():
    p = parse_filename("indium_standard.txt")
    assert p.date is None
    assert not p.has_date
    assert p.description == "indium standard"


def test_invalid_date_is_not_treated_as_date():
    p = parse_filename("2023_13_99_weird.txt")
    assert p.date is None
    assert "2023" in p.tokens
