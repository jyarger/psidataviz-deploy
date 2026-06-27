# Contributing to PsiDataViz

Thanks for your interest! PsiDataViz aims to read, organize, and visualize **every kind of scientific
data** — which is only possible with community contributions. The single most valuable thing you can add
is a **reader for a format we don't yet handle**.

By contributing you agree that your contributions are licensed under the project's
[Apache License 2.0](LICENSE).

## Development setup

Prerequisites: [`uv`](https://docs.astral.sh/uv/) and Node 20+.

```bash
git clone https://github.com/jyarger/PsiDataViz.git
cd PsiDataViz
uv sync --all-packages --all-extras          # Python workspace -> .venv
cd apps/frontend && npm install && cd ../..   # frontend deps
```

## Checks (please run before opening a PR)

```bash
uv run ruff check packages/psidata apps/backend     # lint
uv run pytest packages/psidata/tests apps/backend/tests apps/psidataviz-dash/tests   # tests
cd apps/frontend && npm run build                   # type-check + build the UI
```

CI runs the same checks on every pull request.

## Adding a reader (the high-value path)

A reader is a small class that (a) `sniff()`s a candidate file and returns a 0–1 confidence, and
(b) `read()`s it into the universal `Dataset` model. Register it and the catalog and app pick it up
automatically — no UI changes needed.

1. Read **[docs/adding-a-reader.md](docs/adding-a-reader.md)** and look at an existing reader in
   `packages/psidata/src/psidata/readers/`.
2. Add your reader + a small test fixture under `packages/psidata/tests/`.
3. `sniff()` should be **honest** — only claim high confidence for data you can actually decode, so the
   catalog doesn't mark unreadable files as "supported."

If you have a format that fails to parse but can't write the reader yourself, please open a
**[data-format request](.github/ISSUE_TEMPLATE)** with a sample file or link — that's exactly the
feedback that drives coverage.

## Pull requests

- Branch from `main`, keep PRs focused, and describe what changed and how you verified it.
- Match the surrounding code style; keep `ruff` and the test suite green.
- Be kind and constructive (see the [Code of Conduct](CODE_OF_CONDUCT.md)).
