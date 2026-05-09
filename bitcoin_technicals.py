#!/usr/bin/env python3
"""
Technical-analysis helpers for Bitcoin OHLCV using pandas-ta (API-compatible).

Installation (pick one):

- **Recommended on Python ≥3.12:** ``pip install pandas-ta``
- **Python <3.12 (many macOS setups):** ``pip install pandas-ta-classic``  
  (import name ``pandas_ta_classic``, same ``df.ta`` extension after import)

Examples::

    python bitcoin_technicals.py
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta_module  # type: ignore
except ImportError:  # pragma: no cover
    import pandas_ta_classic as ta_module  # type: ignore

from btc_spot_futures_download import fetch_yfinance_ohlcv

# -----------------------------------------------------------------------------
# Indicator explanations (for docs / CLI)
# -----------------------------------------------------------------------------
INDICATOR_GUIDE: Dict[str, str] = {
    # Trend
    "SMA_*": (
        "Simple moving average — average Close over N days. Filters noise; "
        "crossovers (short vs long) are often used for trend cues."
    ),
    "EMA_*": (
        "Exponential moving average — weights recent closes more heavily than an SMA "
        "of the same length, so it reacts faster to new prices."
    ),
    # Momentum
    "RSI_*": (
        "Relative Strength Index — 0–100 oscillator of gain vs loss speed. "
        "High (>70-ish) suggests strong upside momentum (sometimes overbought); "
        "low (<30-ish) the opposite."
    ),
    "MACD*": (
        "MACD = fast EMA minus slow EMA; signal line is an EMA of MACD; histogram "
        "is MACD minus signal. Used for momentum and crossover-style signals."
    ),
    "STOCH*_k/d": (
        "Stochastic oscillator — where Close sits relative to the high–low range "
        "over k periods (%K), smoothed into %D. Similar spirit to RSI on a bounded scale."
    ),
    # Volatility
    "BBL_/BBM_/BBU_/BBB_/BBP_": (
        "Bollinger Bands — middle line is SMA of Close; upper/lower are typically "
        "±2σ. Band width/expansion indicates volatility; prices near bands can hint "
        "at stretch vs mean."
    ),
    "ATR*_r": (
        "Average True Range — average of “true range” (gap-aware high–low range). "
        "Scale is in price units per bar (not percentages); compares risk/vol regimes."
    ),
    # Volume
    "OBV": (
        "On-Balance Volume — cumulative volume weighted by whether price closed "
        "up/down vs prior close. Helps spot whether volume confirms a move."
    ),
    "VMA_SMA_* / VOL_SMA_*": (
        "Simple moving average of trading volume — smooths bursts to see typical "
        "participation; spikes vs this baseline can highlight unusual activity."
    ),
    # Custom
    "PR_RANGE_PCT": (
        "(High − Low) / Close × 100 — intrabar range as percent of Close; "
        "a simple liquidity/volatility-of-the-day gauge."
    ),
    "ROC_*": (
        "Rate of change (%): (Close_t / Close_{t−n} − 1) × 100 — "
        "direct percent momentum over n bars."
    ),
    "ROLL_VOL_*": (
        "Rolling volatility of daily log returns, annualized (×√365). "
        "Higher = more dispersion in daily moves (crypto traded all week)."
    ),
}


def add_technical_indicators(
    df: pd.DataFrame,
    *,
    rsi_length: int = 14,
    stoch_k: int = 14,
    stoch_d: int = 3,
    smooth_k: int = 3,
    bbands_length: int = 20,
    bbands_std: float = 2.0,
    atr_length: int = 14,
    vol_ma_length: int = 20,
    roc_momentum_length: int = 10,
    rolling_vol_window: int = 20,
    volume_sma_prefix: str = "VMA",
    inplace: bool = False,
) -> pd.DataFrame:
    """
    Append TA columns to Bitcoin (or generic OHLCV) data using pandas-ta / pandas-ta-classic.

    Expects Yahoo-style columns ``Open``, ``High``, ``Low``, ``Close``, optionally
    ``Adj Close``, ``Volume``. The helper works on a **copy** by default because
    ``df.ta`` may normalize column names in place on first access.
    """
    if df.empty:
        raise ValueError("DataFrame is empty.")

    out = df if inplace else df.copy()

    # --- Trend ---
    out.ta.sma(length=20, append=True)
    out.ta.sma(length=50, append=True)
    out.ta.sma(length=200, append=True)
    out.ta.ema(length=12, append=True)
    out.ta.ema(length=26, append=True)

    # --- Momentum ---
    out.ta.rsi(length=rsi_length, append=True)
    out.ta.macd(fast=12, slow=26, signal=9, append=True)
    out.ta.stoch(k=stoch_k, d=stoch_d, smooth_k=smooth_k, append=True)

    # --- Volatility ---
    out.ta.bbands(length=bbands_length, std=bbands_std, mamode="sma", append=True)
    out.ta.atr(length=atr_length, append=True)

    # --- Volume ---
    out.ta.obv(append=True)
    out.ta.sma(
        close="volume",
        length=vol_ma_length,
        prefix=volume_sma_prefix,
        append=True,
    )

    # --- Custom (simple features on top of cleaned prices) ---
    # Column names after first ``.ta`` use may already be lowercase; resolve robustly:
    close = _get_price_series(out, ("adj_close", "close"))
    high = _get_price_series(out, ("high",))
    low = _get_price_series(out, ("low",))

    rng = np.where(close != 0, (high.astype(float) - low.astype(float)) / close.astype(float), np.nan)
    out["PR_RANGE_PCT"] = 100.0 * rng

    out.ta.roc(length=roc_momentum_length, append=True)

    log_ret = np.log(close.astype(float) / close.astype(float).shift(1))
    out[f"ROLL_VOL_{rolling_vol_window}"] = (
        log_ret.rolling(rolling_vol_window).std(ddof=0) * np.sqrt(365.0)
    )

    return out


def _get_price_series(df: pd.DataFrame, candidates: tuple[str, ...]) -> pd.Series:
    """Return first existing column matching candidate names case-insensitively."""
    colmap = {_norm_col(c): c for c in df.columns}
    for cand in candidates:
        key = _norm_col(cand)
        if key in colmap:
            return df[colmap[key]]
    raise KeyError(f"None of the columns {candidates} exist (have: {df.columns.tolist()})")


def _norm_col(name: str) -> str:
    return str(name).strip().lower()


def print_indicator_guide(text: Optional[Dict[str, str]] = None) -> None:
    """Print concise explanations keyed by indicator family."""
    mapping = text or INDICATOR_GUIDE
    print("\nIndicator quick reference:")
    print("-" * 60)
    for key, desc in sorted(mapping.items()):
        print(f"{key}: {desc}\n")


def _resolve_columns(df: pd.DataFrame, labels: List[str]) -> List[str]:
    cmap = {_norm_col(c): c for c in df.columns}
    out: List[str] = []
    for lab in labels:
        key = _norm_col(lab)
        if key in cmap:
            out.append(cmap[key])
            continue
        if lab == "ROLL_VOL_snapshot":
            r = next((cmap[k] for k in cmap if k.startswith("roll_vol_")), None)
            if r:
                out.append(r)
            continue
    return out


def _tail_preview(df: pd.DataFrame, n: int = 3) -> None:
    print(f"\nLast {n} rows (selected columns), newest at bottom:")
    pref = [
        "close",
        "SMA_20",
        "SMA_50",
        "SMA_200",
        "EMA_12",
        "EMA_26",
        "RSI_14",
        "MACD_12_26_9",
        "MACDh_12_26_9",
        "STOCHk_14_3_3",
        "STOCHd_14_3_3",
        "ATRr_14",
        "VMA_SMA_20",
        "OBV",
        "PR_RANGE_PCT",
        "ROC_10",
        "ROLL_VOL_snapshot",
    ]
    cols = _resolve_columns(df, pref)
    if not cols:
        cols = df.columns[-15:].tolist()
    subset = df[cols].tail(n)
    with pd.option_context("display.width", None, "display.max_columns", None):
        print(subset)


def insufficient_history_warning_needed(df: pd.DataFrame) -> Optional[str]:
    if len(df) < 250:
        return (
            "Note: SMA_200 needs ~200 trading days — use period='2y' (or larger) "
            "if you expect a full SMA_200 column."
        )
    return None


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Add pandas-ta indicators to BTC OHLCV data.")
    p.add_argument("--ticker", default="BTC-USD", help="Yahoo Finance ticker (default BTC-USD).")
    p.add_argument(
        "--period",
        default="2y",
        help="yfinance period (default 2y so SMA_200 can populate).",
    )
    p.add_argument("--guide", action="store_true", help="Print explanation of indicators and exit.")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)

    if args.guide:
        print_indicator_guide()
        return

    df = fetch_yfinance_ohlcv(args.ticker, period=args.period)
    note = insufficient_history_warning_needed(df)
    if note:
        print(note)

    enriched = add_technical_indicators(df)
    ta_module_used = getattr(ta_module, "__name__", "pandas_ta")
    ta_ver = getattr(ta_module, "__version__", "?")
    print(f" pandas-ta module: {ta_module_used}, version={ta_ver}")
    print(f" Rows: {len(enriched)}, columns added (sample): {[c for c in enriched.columns if c not in df.columns][:15]}...")
    print(f" Total columns: {len(enriched.columns)}")
    print_indicator_guide()
    _tail_preview(enriched)


if __name__ == "__main__":
    main()
