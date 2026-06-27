# psidata (Ψ Data)

A framework-agnostic Python library to **ingest, parse, and convert experimental & computational
scientific data** into a single universal model — usable directly in marimo / Jupyter, and the core
that powers the **ΨDataViz** web app.

```python
import psidata

ds = psidata.read(psidata.Candidate(filename="run.txt", text=open("run.txt").read()))
print(ds.technique, ds.summary())
```

Built-in readers: **DSC** (TA Trios `.txt`/`.csv`), **NMR** (JCAMP-DX), **FTIR** (`.dpt`/`.csv`),
**Raman** (`.csv`). Add a technique by writing one `@register_reader` reader — see
[`../../docs/adding-a-reader.md`](../../docs/adding-a-reader.md).

Part of the [ΨData](../../README.md) monorepo.
