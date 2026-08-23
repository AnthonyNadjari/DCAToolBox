"""Generate campaign-2 specs: literature-mechanical rules + BASK-data signals.

Every rule below is a DELAY rule in our frame (cash arrives on the month's
first bar; the null deploys it immediately). Sources: the six deep-research
reports (academic, practitioner, FOMC/macro-calendar, vol/options, EUR/UCITS)
and the BASK-sourced Bloomberg families. max_hold caps the wait per the
literature's own justification; fill is "open" unless the rule's mechanism
demands the close.
"""

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
    # --- FOMC / announcement calendar (Lucca-Moench, Savor-Wilson, Kurov) ---
    s("lit_prefomc_any", [("days_to_fomc", "<", 1.5)], 63),
    s("lit_prefomc_cap10", [("days_to_fomc", "<", 1.5)], 10),
    s("lit_prefomc_vixgate", [("days_to_fomc", "<", 1.5), ("vix_now", ">", 20)], 10),
    s("lit_fomc_eve_close", [("days_to_fomc", "<", 1.5)], 10, fill="close"),
    s("lit_nfp_eve", [("days_to_nfp", "<", 1.5)], 5),
    s("lit_nfp_eve_close", [("days_to_nfp", "<", 1.5)], 5, fill="close"),
    s("lit_fomc_even_week", [("fomc_even_week", ">", 0.5)], 10),
    # --- turn-of-month / dash-for-cash (McConnell-Xu, Etula RFS 2020) ---
    s(
        "lit_tom_t4",
        [("tdays_to_month_end", "<", 3.5), ("tdays_to_month_end", ">", 2.5)],
        63,
        fill="close",
    ),
    s("lit_tom_t4_open", [("tdays_to_month_end", "<", 3.5), ("tdays_to_month_end", ">", 2.5)], 63),
    s(
        "lit_tom_t2",
        [("tdays_to_month_end", "<", 1.5), ("tdays_to_month_end", ">", 0.5)],
        63,
        fill="close",
    ),
    s("lit_tom_window", [("tdays_to_month_end", "<", 3.5)], 63),
    # --- OpEx (Stivers-Sun, Quantpedia) ---
    s("lit_opex_entry", [("days_to_opex", "<", 7.5), ("days_to_opex", ">", 2.5)], 15),
    s("lit_avoid_postopex", [("post_opex_week", "<", 0.5)], 63),
    # --- short-horizon oversold with hard caps (Connors RSI2) ---
    s("lit_rsi2_trend_cap5", [("rsi_2", "<", 10), ("sma_ratio_200", ">", 0.0)], 5),
    s("lit_rsi2_trend_cap10", [("rsi_2", "<", 10), ("sma_ratio_200", ">", 0.0)], 10),
    s("lit_rsi2_deep_cap5", [("rsi_2", "<", 5), ("sma_ratio_200", ">", 0.0)], 5),
    s("lit_2down_cap5", [("down_streak", ">", 1.5), ("sma_ratio_200", ">", 0.0)], 5),
    s("lit_dip2_cap10", [("ret_5", "<", -0.02)], 10),
    # --- volatility literature (Bansal-Stivers, Fassas, Goepfert) ---
    s("lit_vix_p80_cap21", [("vix_pctl", ">", 0.8)], 21),
    s("lit_vix_p80_cap10", [("vix_pctl", ">", 0.8)], 10),
    s("lit_backwardation_cap5", [("vix_ts", ">", 0.0)], 5),
    s("lit_volcrush_bearkiller", [("vix_peak_63", ">", 50), ("vix_now", "<", 30)], 63),
    s("lit_vix40_wait", [("vix_now", ">", 40)], 63),
    s(
        "lit_vix30_relief",
        [("vix_peak_63", ">", 30), ("vix_now", "<", 30), ("vix_chg_5", "<", 0)],
        21,
    ),
    # --- BASK families: CFTC positioning (contrarian) ---
    s("bask_cftc_pctl_low", [("cftc_pctl", "<", 0.1)], 63),
    s("bask_cftc_z_low", [("cftc_z_1y", "<", -1.5)], 63),
    s("bask_cftc_z_low_cap21", [("cftc_z_1y", "<", -1.5)], 21),
    # --- NAAIM manager capitulation ---
    s("bask_naaim_low", [("naaim_pctl", "<", 0.1)], 63),
    s("bask_naaim_sub30", [("naaim", "<", 30)], 63),
    s("bask_naaim_low_cap21", [("naaim_pctl", "<", 0.1)], 21),
    # --- short interest (Rapach et al.: high SI = low future returns) ---
    s("bask_si_low", [("si_pctl", "<", 0.5)], 63),
    s("bask_si_not_extreme", [("si_pctl", "<", 0.9)], 63),
    # --- ETF flow capitulation ---
    s("bask_flow_outflow", [("spy_flow_21", "<", -1.0)], 63),
    s("bask_flow_outflow_cap21", [("spy_flow_21", "<", -1.0)], 21),
    s("bask_flow_pctl_low", [("spy_flow_pctl", "<", 0.1)], 63),
    # --- earnings revisions / valuation ---
    s("bask_eps_up", [("eps_rev_21", ">", 0.0)], 21),
    s("bask_eps_capitulation", [("eps_rev_63", "<", -0.03)], 63),
    s("bask_fedmodel_cheap", [("fed_model_pctl", ">", 0.8)], 63),
    s("bask_fedmodel_cheap_cap21", [("fed_model_pctl", ">", 0.8)], 21),
    # --- implied correlation spikes (Cboe, Buss et al.) ---
    s("bask_implcorr_spike", [("impl_corr_pctl", ">", 0.9)], 63),
    s("bask_implcorr_jump", [("impl_corr_chg_21", ">", 10)], 63),
    s("bask_implcorr_spike_cap21", [("impl_corr_pctl", ">", 0.9)], 21),
    # --- cross-family combos flagged by multiple reports ---
    s("combo_tom_dip", [("tdays_to_month_end", "<", 3.5), ("dd_63", "<", -0.02)], 63),
    s("combo_fomc_flow", [("days_to_fomc", "<", 1.5), ("spy_flow_21", "<", 0.0)], 21),
    s("combo_vix_cftc", [("vix_pctl", ">", 0.8), ("cftc_z_1y", "<", -1.0)], 21),
    s("combo_naaim_dip", [("naaim_pctl", "<", 0.2), ("dd_63", "<", -0.03)], 63),
    s("combo_eps_dip", [("eps_rev_21", ">", 0.0), ("dd_63", "<", -0.03)], 21),
]

out = Path(__file__).parent / "campaign2.json"
json.dump(SPECS, out.open("w"), indent=1)
print(f"{len(SPECS)} campaign-2 specs -> {out}")
