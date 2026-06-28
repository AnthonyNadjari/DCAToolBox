"""Assemble the static GitHub Pages site for DCAToolBox.

The published site is a fully client-side, interactive backtester: the Python
engine is mirrored in JavaScript (parity-tested) and runs in the browser, while
this script only prepares the assets:

* fetches and bundles market data into ``site/data/`` (see ``bundle_data.py``),
* copies the web app (``web/*.html``, ``*.js``, ``*.css``) into ``site/``,
* writes a ``.nojekyll`` marker.

Run locally with::

    PYTHONPATH=. python scripts/build_site.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import bundle_data  # sibling module (scripts/ is on sys.path when run as a script)

SITE = Path("site")
WEB = Path("web")
ASSET_GLOBS = ("*.html", "*.js", "*.css")


def build() -> Path:
    """Build the full static site under ``site/`` and return that path."""
    SITE.mkdir(parents=True, exist_ok=True)
    bundle_data.main()
    for pattern in ASSET_GLOBS:
        for asset in WEB.glob(pattern):
            shutil.copy2(asset, SITE / asset.name)
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    return SITE


if __name__ == "__main__":
    out = build()
    print(f"Site assembled at {out.resolve()}")
