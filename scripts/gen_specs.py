"""Generate the exhaustive signal grid for signal_lab.

Every feature in the lab's library x 20 quantile thresholds x both directions
(single conditions), plus a seeded set of random two-condition ANDs. Thresholds
are the feature's own IN-SAMPLE quantiles (computed on data through IS_END
only), so the grid is identical no matter when it is regenerated.

Usage::

    PYTHONPATH=. python scripts/gen_specs.py --out specs.json [--pairs 1000]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.signal_lab import IS_END, build_features

QUANTILES = [round(q, 3) for q in np.linspace(0.05, 0.95, 20)]


def make_specs(pairs: int, seed: int = 7) -> list[dict]:
    """Single-condition grid + seeded random two-condition ANDs."""
    spy, feats = build_features()
    cut = spy.index.searchsorted(pd.Timestamp(IS_END), side="right")
    specs: list[dict] = []
    thresholds: dict[str, list[float]] = {}
    for name, arr in sorted(feats.items()):
        x = arr[:cut]
        x = x[np.isfinite(x)]
        if len(x) < 500:
            continue
        qs = sorted({float(np.quantile(x, q)) for q in QUANTILES})
        thresholds[name] = qs
        for thr in qs:
            for op in (">", "<"):
                specs.append(
                    {
                        "name": f"{name}{op}{thr:.4g}",
                        "conds": [{"feature": name, "op": op, "thr": thr}],
                        "base_deploy": 0.0,
                    }
                )
    rng = random.Random(seed)
    names = sorted(thresholds)
    for k in range(pairs):
        f1, f2 = rng.sample(names, 2)
        c1 = {"feature": f1, "op": rng.choice([">", "<"]), "thr": rng.choice(thresholds[f1])}
        c2 = {"feature": f2, "op": rng.choice([">", "<"]), "thr": rng.choice(thresholds[f2])}
        specs.append({"name": f"and{k}", "conds": [c1, c2], "base_deploy": 0.0})
    return specs


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="specs.json")
    ap.add_argument("--pairs", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    specs = make_specs(args.pairs, args.seed)
    Path(args.out).write_text(json.dumps(specs))
    print(f"wrote {args.out}: {len(specs)} specs")


if __name__ == "__main__":
    main()
