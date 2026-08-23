"""Campaign 2b: the final research agent's top untested candidates."""

import json
from pathlib import Path


def s(name, conds, max_hold=63, base_deploy=0.0, fill="open"):
    return {
        "name": name,
        "conds": [{"feature": f, "op": o, "thr": t} for f, o, t in conds],
        "max_hold": max_hold,
        "base_deploy": base_deploy,
        "fill": fill,
    }


SPECS = [
    # VRP (Bollerslev-Tauchen-Zhou): defer while VRP negative, deploy when positive
    s("vrp_wait_pos_cap10", [("vrp", ">", 0.0)], 10),
    s("vrp_wait_pos_cap21", [("vrp", ">", 0.0)], 21),
    s("vrp_top_quartile", [("vrp_q_3y", ">", 0.75)], 21),
    s("vrp_top_quartile_cap10", [("vrp_q_3y", ">", 0.75)], 10),
    s("vrp_pos_after_spike", [("vrp", ">", 0.0), ("vix_peak_63", ">", 30)], 21),
    # MOVE-VIX divergence (IRFA 2026): defer while MOVE stressed vs VIX
    s("movevix_calm_cap10", [("move_vix_div", "<", 0.5)], 10),
    s("movevix_calm_cap21", [("move_vix_div", "<", 0.5)], 21),
    s("movevix_extreme_wait", [("move_vix_div", "<", 1.5)], 21),
    # Davies speculation sentiment: defer while leveraged-long creation high
    s("specsent_low_cap21", [("spec_sent", "<", 0.0)], 21),
    s("specsent_capitulation", [("spec_sent", "<", -1.0)], 63),
    s("specsent_not_high", [("spec_sent", "<", 1.0)], 21),
]
out = Path(__file__).parent / "campaign2b.json"
json.dump(SPECS, out.open("w"), indent=1)
print(f"{len(SPECS)} specs -> {out}")
