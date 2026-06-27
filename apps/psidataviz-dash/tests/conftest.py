from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def dsc_txt() -> str:
    return (FIXTURES / "dsc_indium_trimmed.txt").read_text(encoding="utf-8")
