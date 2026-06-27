# Adding a data reader

A *reader* teaches ΨData how to parse one file format into the universal
[`Dataset`](../packages/psidata/src/psidata/model.py) container. Once registered, it works everywhere — the
catalog flags matching files, the app plots them, and the marimo/Colab exports reproduce them.
**You never edit the registry, the app, or the data model** — you just add one file.

## The contract

Subclass `BaseReader` and implement two methods:

| Method | Returns | Purpose |
| --- | --- | --- |
| `sniff(candidate)` | `float` in `[0, 1]` | How confident are you that this file is yours? The registry picks the highest score above `DETECT_THRESHOLD` (0.4). |
| `read(candidate)` | `Dataset` | Fully parse the file. |

A `Candidate` gives you `.filename`, `.ext`, `.stem`, and the content via `.as_text()` /
`.head(n)` (decoding is handled for you).

Set these class attributes:

- `technique` — the instrument/method label; **match the data folder name** (e.g. `"FTIR"`), so the
  catalog can group and pre-flag files.
- `name`, `version` — identify the reader (recorded in `Dataset.source`).
- `extensions` — a tuple used for cheap catalog pre-filtering (real detection still uses `sniff`).

## Skeleton: an FTIR reader

```python
# packages/psidata/src/psidata/readers/ftir_csv.py
from __future__ import annotations

import io
import pandas as pd

from ..model import Axis, Dataset, Metadata, Signal, SourceInfo
from ..registry import register_reader
from .base import BaseReader, Candidate


@register_reader
class FtirCsvReader(BaseReader):
    technique = "FTIR"
    name = "ftir_csv"
    version = "0.1.0"
    extensions = (".csv", ".dpt", ".txt")

    def sniff(self, candidate: Candidate) -> float:
        head = candidate.head(2000).lower()
        score = 0.2 if candidate.ext in self.extensions else 0.0
        if "wavenumber" in head or "cm-1" in head or "cm^-1" in head:
            score += 0.6
        return min(score, 1.0)

    def read(self, candidate: Candidate) -> Dataset:
        df = pd.read_csv(io.StringIO(candidate.as_text()))
        x_col, y_col = df.columns[0], df.columns[1]
        signal = Signal(
            name="spectrum",
            x=Axis(label=x_col, unit="cm⁻¹", quantity="wavenumber"),
            y=Axis(label=y_col, unit="a.u.", quantity="absorbance"),
            frame=df,
        )
        return Dataset(
            technique=self.technique,
            source=SourceInfo(uri=candidate.uri, filename=candidate.filename,
                              reader=self.name, reader_version=self.version),
            metadata=Metadata(sample_name=candidate.stem),
            signals=[signal],
        )
```

## Register it

Add one import so the module loads (which runs the `@register_reader` decorator):

```python
# packages/psidata/src/psidata/readers/__init__.py
from . import dsc_trios, ftir_csv  # noqa: F401
```

## Test it

Drop a small real export under `packages/psidata/tests/fixtures/` and assert on the parsed `Dataset` — mirror the
style of [`tests/test_dsc_reader.py`](../packages/psidata/tests/test_dsc_reader.py). At minimum: the registry detects
it (`detect`/`read`), metadata fields are populated, and the signal frames hold numeric data.

## Tips

- **Header-heavy formats (DSC, NMR):** parse the header into metadata; put critical context
  (units, segments, acquisition params) on a technique-specific `Metadata` subclass — see
  `DSCMetadata` in [`dsc_trios.py`](../packages/psidata/src/psidata/readers/dsc_trios.py).
- **Multi-trace data:** emit one `Signal` per curve/segment (DSC uses one per thermal ramp).
- **Keep `read` pure:** no network, no global state. The source layer fetches bytes; you parse them.
