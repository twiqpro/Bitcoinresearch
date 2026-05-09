#!/usr/bin/env python3
"""
Download BTC spot (BTC-USD) and CME BTC futures proxy (BTC=F) from Yahoo Finance,
clean into indexed DataFrames, and print summaries.

Dependencies: pandas, yfinance, numpy, scikit-learn, plotly
  pip install pandas yfinance numpy scikit-learn plotly
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd
import plotly
import sklearn
import yfinance as yf

_OHLCV_FIELDS = frozenset({"Open", "High", "Low", "Close", "Adj Close", "Volume"})


def _flatten_columns(cols: pd.Index) -> pd.Index:
    if not isinstance(cols, pd.MultiIndex):
        return cols
    for level in range(cols.nlevels):
        values = set(cols.get_level_values(level))
        if values & _OHLCV_FIELDS:
            return cols.get_level_values(level)
    return cols.get_level_values(0)


def fetch_yfinance_ohlcv(
    ticker: str,
    period: Optional[str] = "2y",
    interval: str = "1d",
    start: Union[str, pd.Timestamp, None] = None,
    end: Union[str, pd.Timestamp, None] = None,
    *,
    allow_empty: bool = False,
) -> pd.DataFrame:
    """Download OHLCV for one symbol and return a flat, datetime-indexed DataFrame.

    Use ``period`` alone, **or** ``start`` / ``end`` (``period`` is ignored when ``start``
    is set).
    """
    dl_kw: Dict[str, Any] = {
        "interval": interval,
        "auto_adjust": False,
        "progress": False,
        "threads": True,
    }
    if start is not None:
        dl_kw["start"] = start
        if end is not None:
            dl_kw["end"] = end
    else:
        dl_kw["period"] = period if period is not None else "2y"

    raw = yf.download(
        ticker,
        **dl_kw,
    )
    if raw.empty:
        if allow_empty:
            return pd.DataFrame()
        raise ValueError(f"No data returned for {ticker!r}")

    raw.columns = _flatten_columns(raw.columns)

    df = raw.copy()
    df.columns = pd.Index(df.columns.astype(str))  # do not pass name as 2nd positional (pandas uses dtype there)
    df.columns.name = None
    df.index = pd.to_datetime(df.index, utc=False)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.index.name = "Date"
    return df


def summarize_frame(name: str, df: pd.DataFrame) -> None:
    print(f"\n{'=' * 60}")
    print(f"{name} — shape: {df.shape[0]} rows × {df.shape[1]} columns")
    print(f"Index: {type(df.index).__name__}, dtype={df.index.dtype}, monotonic={df.index.is_monotonic_increasing}")
    print("\n--- Missing values per column ---")
    miss = df.isna().sum()
    print(miss.to_string())
    total_na = int(miss.sum())
    print(f"Total NaN cells: {total_na}")

    print("\n--- Basic statistics (numeric columns) ---")
    # numpy/sklearn available for downstream work; describe uses pandas/numpy internally
    print(df.describe().to_string())

    print("\n--- Head (5) ---")
    print(df.head().to_string())
    print("\n--- Tail (5) ---")
    print(df.tail().to_string())


def main() -> None:
    # Libraries requested by user (sklearn, plotly imported at module level)
    _ = (np, sklearn, plotly)  # explicit reference so imports are not "unused" in strict linters

    spot = fetch_yfinance_ohlcv("BTC-USD", period="2y")
    futures = fetch_yfinance_ohlcv("BTC=F", period="2y")

    summarize_frame("BTC-USD (spot)", spot)
    summarize_frame("BTC=F (futures)", futures)

    # Optional alignment check: overlapping calendar dates
    overlap = spot.index.intersection(futures.index)
    print(f"\n{'=' * 60}")
    print(f"Overlapping trading dates (intersection): {len(overlap)}")


if __name__ == "__main__":
    main()
