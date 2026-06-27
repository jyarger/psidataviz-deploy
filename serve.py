"""Run the PsiDataViz (Dash) dev server without relying on editable installs:

    python serve.py

Injects both workspace ``src/`` dirs onto the path, then starts the app. Handy on machines where
the interpreter doesn't reliably honor editable-install ``.pth`` files. For production, use gunicorn
against ``psidataviz_dash.server:server`` (see docs/deploy.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _src in (_ROOT / "packages/psidata/src", _ROOT / "apps/psidataviz-dash/src"):
    sys.path.insert(0, str(_src))

from psidataviz_dash.server import main  # noqa: E402

if __name__ == "__main__":
    main()
