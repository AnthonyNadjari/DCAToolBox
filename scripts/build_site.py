"""Assemble the static GitHub Pages site for DCAToolBox.

The published site is "Le Signal": a single static page showing the plan's one
monthly instruction (risk on/off vs the 200-day average) and its evidence. All
data is precomputed locally into ``web/data.json`` (``scripts/build_signal_page.py``,
requires the Bloomberg caches); this script only copies assets and writes a
``.nojekyll`` marker.

Run locally with::

    PYTHONPATH=. python scripts/build_site.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

SITE = Path("site")
WEB = Path("web")
ASSET_GLOBS = ("*.html", "*.js", "*.css", "*.svg", "*.json")


def build() -> Path:
    """Build the full static site under ``site/`` and return that path."""
    SITE.mkdir(parents=True, exist_ok=True)
    for pattern in ASSET_GLOBS:
        for asset in WEB.glob(pattern):
            shutil.copy2(asset, SITE / asset.name)
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    return SITE


if __name__ == "__main__":
    out = build()
    print(f"Site assembled at {out.resolve()}")
