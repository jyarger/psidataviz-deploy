from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def dsc_txt_path() -> Path:
    return FIXTURES / "dsc_indium_trimmed.txt"


@pytest.fixture
def dsc_txt(dsc_txt_path: Path) -> str:
    return dsc_txt_path.read_text(encoding="utf-8")


@pytest.fixture
def dsc_csv_path() -> Path:
    return FIXTURES / "dsc_acetaminophen_trimmed.csv"


@pytest.fixture
def dsc_csv(dsc_csv_path: Path) -> str:
    return dsc_csv_path.read_text(encoding="utf-8")


@pytest.fixture
def nmr_txt_path() -> Path:
    return FIXTURES / "nmr_agilent_trimmed.txt"


@pytest.fixture
def nmr_txt(nmr_txt_path: Path) -> str:
    return nmr_txt_path.read_text(encoding="utf-8")


@pytest.fixture
def ftir_dpt() -> str:
    return (FIXTURES / "ftir_cbd_trimmed.dpt").read_text(encoding="utf-8")


@pytest.fixture
def raman_csv() -> str:
    return (FIXTURES / "raman_cbd_trimmed.csv").read_text(encoding="utf-8")
