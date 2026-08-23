"""Generate the exhaustive single-condition spec grid (mechanical layer).

For every feature: fire when the feature is above/below each of a fixed set of
its own in-sample quantiles. Zero human choice — the multiplicity is known
exactly, so chance-level survival rates can be stated.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from features import build_features

QUANTILES = [0.02, 0.05, 0.1, 0.25, 0.75, 0.9, 0.95, 0.98]
IS_END = "2013-09-15"


def main() -> None:
    asset, feats = build_features()
    cut = asset.index.searchsorted(pd.Timestamp(IS_END), side="right")
    specs = []
    for name, x in sorted(feats.items()):
        xs = x[:cut]
        xs = xs[np.isfinite(xs)]
        if len(xs) < 500:
            continue
        for q in QUANTILES:
            thr = float(np.quantile(xs, q))
            op = "<" if q < 0.5 else ">"
            specs.append({"name": f"grid_{name}_{op}_q{int(q*100):02d}",
                          "conds": [{"feature": name, "op": op, "thr": round(thr, 6)}],
                          "base_deploy": 0.0})
    out = Path(__file__).parent / "specs" / "grid.json"
    out.write_text(json.dumps(specs, indent=0))
    print(f"{len(specs)} grid specs -> {out}")


if __name__ == "__main__":
    main()
