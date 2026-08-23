"""Campaign 2c: money-market-fund cash gauge (trader's suggestion)."""
import json
from pathlib import Path


def s(name, conds, max_hold=63):
    return {"name": name, "conds": [{"feature": f, "op": o, "thr": t} for f, o, t in conds],
            "max_hold": max_hold, "base_deploy": 0.0, "fill": "open"}


SPECS = [
    s("mmf_surge_13w", [("mmf_growth_13w", ">", 0.04)]),              # cash piling in = fear
    s("mmf_surge_4w", [("mmf_growth_4w", ">", 0.02)]),
    s("mmf_spx_high_z", [("mmf_spx_z_3y", ">", 1.0)]),                # cash big vs equities
    s("mmf_spx_extreme", [("mmf_spx_z_3y", ">", 2.0)]),
    s("mmf_spx_pctl_high", [("mmf_spx_pctl", ">", 0.9)]),
    s("mmf_surge_dip", [("mmf_growth_13w", ">", 0.03), ("dd_63", "<", -0.03)]),
    s("mmf_surge_cap21", [("mmf_growth_13w", ">", 0.04)], 21),
    s("mmf_z_cap21", [("mmf_spx_z_3y", ">", 1.0)], 21),
    s("mmf_peak_rollover", [("mmf_growth_4w", "<", 0.0), ("mmf_spx_z_3y", ">", 1.0)]),  # cash starts leaving MMFs
]
out = Path(__file__).parent / "campaign2c.json"
json.dump(SPECS, out.open("w"), indent=1)
print(f"{len(SPECS)} specs -> {out}")
