"""Data universe manifest for the direct-Bloomberg research program.

Every series the campaigns may use is declared here once, with its fields and
earliest requested date. Pulled data is cached under ``data_bbg/`` (gitignored:
Bloomberg data must never be committed to the public repository).
"""

from __future__ import annotations

OHLCV = ["PX_OPEN", "PX_HIGH", "PX_LOW", "PX_LAST", "PX_VOLUME"]
LAST = ["PX_LAST"]

#: ticker -> (fields, start date)
DAILY_UNIVERSE: dict[str, tuple[list[str], str]] = {
    # --- the actual instrument (EUR, Euronext) and its leveraged sibling ---
    "ESE FP Equity": (
        OHLCV
        + ["PX_BID", "PX_ASK", "FUND_NET_ASSET_VAL", "TOT_RETURN_INDEX_GROSS_DVDS", "EQY_SH_OUT"],
        "2013-09-16",
    ),
    "CL2 FP Equity": (
        OHLCV + ["PX_BID", "PX_ASK", "FUND_NET_ASSET_VAL", "TOT_RETURN_INDEX_GROSS_DVDS"],
        "2009-01-01",
    ),
    "LQQ FP Equity": (
        OHLCV + ["PX_BID", "PX_ASK", "FUND_NET_ASSET_VAL", "TOT_RETURN_INDEX_GROSS_DVDS"],
        "2009-01-01",
    ),
    "SPY US Equity": (OHLCV + ["TOT_RETURN_INDEX_GROSS_DVDS"], "1993-01-29"),
    # --- underlying indices (long history for backfill) ---
    "SPX Index": (OHLCV, "1960-01-01"),
    "SPXT Index": (LAST, "1988-01-01"),  # S&P 500 total return
    "SX5E Index": (OHLCV, "1990-01-01"),
    "NDX Index": (OHLCV, "1985-01-01"),
    "XNDX Index": (LAST, "1999-01-01"),  # Nasdaq-100 total return
    # --- FX (the EUR investor's lens) ---
    "EURUSD Curncy": (OHLCV[:4], "1975-01-01"),
    "DXY Curncy": (LAST, "1975-01-01"),
    "EURUSDV1M Curncy": (LAST, "1999-01-01"),  # 1M implied vol
    "EURUSD25R1M Curncy": (LAST, "1999-01-01"),  # 1M 25-delta risk reversal
    # --- volatility complex ---
    "VIX Index": (OHLCV[:4], "1990-01-01"),
    "VIX3M Index": (LAST, "2002-01-01"),
    "VVIX Index": (LAST, "2007-01-01"),
    "V2X Index": (LAST, "1999-01-01"),
    "MOVE Index": (LAST, "1988-01-01"),
    "SKEW Index": (LAST, "1990-01-01"),
    "UX1 Index": (LAST, "2004-01-01"),  # VIX futures generics
    "UX2 Index": (LAST, "2004-01-01"),
    "UX3 Index": (LAST, "2004-01-01"),
    # --- rates & credit ---
    "USGG3M Index": (LAST, "1980-01-01"),
    "USGG2YR Index": (LAST, "1980-01-01"),
    "USGG10YR Index": (LAST, "1980-01-01"),
    "GTDEM10Y Govt": (LAST, "1990-01-01"),
    "ESTRON Index": (LAST, "2019-10-01"),
    "FDTR Index": (LAST, "1980-01-01"),
    "USSOC Curncy": (LAST, "2000-01-01"),
    "LF98OAS Index": (LAST, "1994-01-01"),  # US HY OAS
    "LUACOAS Index": (LAST, "1989-01-01"),  # US IG OAS
    "CDX HY CDSI GEN 5Y SPRD Corp": (LAST, "2004-01-01"),
    # --- sentiment / positioning / breadth ---
    "AAIIBULL Index": (LAST, "1987-07-01"),
    "AAIIBEAR Index": (LAST, "1987-07-01"),
    "PCUSEQTR Index": (LAST, "2003-01-01"),  # CBOE equity put/call
    "ADLN Index": (LAST, "1990-01-01"),  # NYSE advance-decline line
    "NFCIINDX Index": (LAST, "1973-01-01"),  # Chicago Fed NFCI (weekly)
    # --- macro surprises & cross-asset ---
    "CESIUSD Index": (LAST, "2003-01-01"),
    "CESIEUR Index": (LAST, "2003-01-01"),
    "ES1 Index": (OHLCV[:4], "1997-01-01"),  # e-mini front future
    "CL1 Comdty": (LAST, "1983-01-01"),
    "HG1 Comdty": (LAST, "1988-01-01"),
    "XAU Curncy": (LAST, "1975-01-01"),
}
