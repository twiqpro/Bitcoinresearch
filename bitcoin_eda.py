#!/usr/bin/env python3
"""
Exploratory data analysis for Bitcoin spot (and optional CME futures proxy).

Generates interactive Plotly HTML charts:
  1) Price / returns / rolling volatility
  2) Return autocorrelation (pattern vs near-white-noise bands)
  3) Calendar effects: hour (hourly bars), day-of-week, month (daily returns)
  4) Feature correlation heatmap (numeric columns from enriched spot data)
  5) Spot vs futures level and spread

Example::

    python bitcoin_eda.py --output eda_output
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bitcoin_technicals import add_technical_indicators
from btc_spot_futures_download import fetch_yfinance_ohlcv

SPOT_TICKER = "BTC-USD"
FUT_TICKER = "BTC=F"


def _normalize_col_lookup(df: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower(): c for c in df.columns}


def _series(df: pd.DataFrame, *names: str) -> pd.Series:
    cmap = _normalize_col_lookup(df)
    for n in names:
        k = n.lower()
        if k in cmap:
            return pd.to_numeric(df[cmap[k]], errors="coerce")
    raise KeyError(f"None of {names} found; columns={df.columns.tolist()}")


def _log_returns(close: pd.Series) -> pd.Series:
    lr = np.log(close.astype(float)).diff()
    lr.name = "log_return"
    return lr


def _simple_returns(close: pd.Series) -> pd.Series:
    r = close.astype(float).pct_change()
    r.name = "simple_return"
    return r


def acf_values(series: pd.Series, max_lag: int) -> Tuple[np.ndarray, np.ndarray]:
    s = series.dropna()
    n = len(s)
    lags = np.arange(1, max_lag + 1)
    vals = np.array([s.autocorr(lag=int(k)) for k in lags], dtype=float)
    return lags, vals


def bartlett_band(n: int, max_lag: int) -> float:
    """Approx 95% band for ACF if series were white noise: ~2/sqrt(n)."""
    if n <= 1:
        return 1.0
    return 2.0 / np.sqrt(n)


def build_feature_frame(spot_daily: pd.DataFrame) -> pd.DataFrame:
    """Spot OHLCV + technicals (numeric columns for correlation)."""
    enriched = add_technical_indicators(spot_daily)
    num = enriched.select_dtypes(include=[np.number])
    na_frac = num.isna().mean()
    keep = na_frac[na_frac < 0.45].index.tolist()
    num = num[keep]
    if num.shape[1] > 42:
        var = num.var().sort_values(ascending=False)
        num = num[var.index[:42]]
    return num


def fig_price_returns_vol(
    spot_daily: pd.DataFrame,
    *,
    vol_window: int = 30,
    title: str = "BTC spot — price, returns, volatility",
) -> go.Figure:
    close = _series(spot_daily, "adj_close", "close")
    lr = _log_returns(close).dropna()
    roll_vol = lr.rolling(vol_window).std(ddof=0) * np.sqrt(365.0)

    fig = make_subplots(
        rows=3,
        cols=1,
        subplot_titles=(
            "Close price — distribution (USD)",
            "Daily log-return distribution (histogram, %)",
            f"Rolling annualized volatility (log returns, {vol_window}d)",
        ),
        vertical_spacing=0.08,
    )
    fig.add_trace(
        go.Histogram(x=close, nbinsx=70, name="Close USD", marker_color="#1f77b4"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Histogram(x=lr * 100.0, nbinsx=80, name="log ret %", marker_color="#2ca02c"),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=roll_vol.index,
            y=roll_vol,
            name="Ann. vol",
            line=dict(color="#d62728"),
        ),
        row=3,
        col=1,
    )
    fig.update_xaxes(title_text="Price (USD)", row=1, col=1)
    fig.update_xaxes(title_text="Log return (%)", row=2, col=1)
    fig.update_xaxes(title_text="Date", row=3, col=1)
    fig.update_yaxes(title_text="Count", row=1, col=1)
    fig.update_yaxes(title_text="Count", row=2, col=1)
    fig.update_yaxes(title_text="σ (ann.)", row=3, col=1)
    fig.update_layout(height=900, title_text=title, showlegend=False)
    return fig


def fig_autocorr(
    spot_daily: pd.DataFrame,
    *,
    max_lag: int = 50,
    title: str = "Autocorrelation of daily log returns",
) -> go.Figure:
    close = _series(spot_daily, "adj_close", "close")
    lr = _log_returns(close).dropna()
    lags, vals = acf_values(lr, max_lag)
    band = bartlett_band(len(lr), max_lag)

    fig = go.Figure()
    fig.add_bar(x=lags, y=vals, name="ACF", marker_color="#9467bd")
    fig.add_hline(y=band, line_dash="dash", line_color="gray", annotation_text="≈95% white-noise")
    fig.add_hline(y=-band, line_dash="dash", line_color="gray")
    fig.add_hline(y=0, line_color="black", line_width=1)
    fig.update_layout(
        title=title,
        xaxis_title="Lag (days)",
        yaxis_title="Autocorrelation",
        height=480,
        bargap=0.15,
    )
    return fig


def fig_calendar_effects(
    spot_daily: pd.DataFrame,
    hourly: pd.DataFrame,
    *,
    title: str = "Calendar effects (returns)",
) -> go.Figure:
    close_d = _series(spot_daily, "adj_close", "close")
    rd = _log_returns(close_d).dropna()
    idx = rd.index
    dow = pd.Series(rd.values, index=idx).groupby(idx.dayofweek).mean()
    dow.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    month = pd.Series(rd.values, index=idx).groupby(idx.month).mean()
    month.index = [f"M{m:02d}" for m in month.index]

    hour_bar: Optional[go.Bar] = None
    if not hourly.empty:
        try:
            ch = _series(hourly, "adj_close", "close")
            rh = np.log(ch.astype(float)).diff().dropna()
            hh = pd.Series(rh.values, index=rh.index).groupby(rh.index.hour).mean()
            hour_vals = hh.reindex(range(24))
            hour_bar = go.Bar(
                x=list(range(24)),
                y=(hour_vals.fillna(0.0).values * 100.0),
                name="hour",
                marker_color="#17becf",
            )
        except KeyError:
            hour_bar = None

    dow_x, dow_y = dow.index.tolist(), (dow.values * 100.0).tolist()
    month_x, month_y = month.index.tolist(), (month.values * 100.0).tolist()

    if hour_bar is not None:
        fig = make_subplots(
            rows=1,
            cols=3,
            subplot_titles=(
                "Hour of day — mean hourly log return (%)",
                "Day of week — mean daily log return (%)",
                "Calendar month — mean daily log return (%)",
            ),
        )
        fig.add_trace(hour_bar, row=1, col=1)
        fig.add_trace(
            go.Bar(x=dow_x, y=dow_y, name="dow", marker_color="#bcbd22"),
            row=1,
            col=2,
        )
        fig.add_trace(
            go.Bar(x=month_x, y=month_y, name="month", marker_color="#e377c2"),
            row=1,
            col=3,
        )
        fig.update_xaxes(title_text="Hour (index hour)", row=1, col=1)
        fig.update_xaxes(title_text="Weekday", row=1, col=2)
        fig.update_xaxes(title_text="Month", row=1, col=3)
        fig.update_yaxes(title_text="Mean log ret (%)", row=1, col=1)
        fig.update_yaxes(title_text="Mean log ret (%)", row=1, col=2)
        fig.update_yaxes(title_text="Mean log ret (%)", row=1, col=3)
        fig.update_layout(
            height=460,
            title_text=title,
            showlegend=False,
            margin=dict(t=100, b=60),
        )
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.5,
            y=-0.18,
            showarrow=False,
            font=dict(size=11),
            text=(
                "Hourly chart: per-hour mean of log returns on 1h bars (timestamp hour from data feed). "
                "Daily charts: from daily log closes (includes Sat/Sun)."
            ),
        )
    else:
        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Day of week — mean daily log return (%)", "Month — mean daily log return (%)"),
        )
        fig.add_trace(
            go.Bar(x=dow_x, y=dow_y, name="dow", marker_color="#bcbd22"),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Bar(x=month_x, y=month_y, name="month", marker_color="#e377c2"),
            row=1,
            col=2,
        )
        fig.update_xaxes(title_text="Weekday", row=1, col=1)
        fig.update_xaxes(title_text="Month", row=1, col=2)
        fig.update_yaxes(title_text="Mean log ret (%)", row=1, col=1)
        fig.update_yaxes(title_text="Mean log ret (%)", row=1, col=2)
        fig.update_layout(
            height=420,
            title_text=f"{title} (no hourly data — widen hourly period or check network)",
            showlegend=False,
        )

    return fig


def fig_correlation_heatmap(num_df: pd.DataFrame, *, title: str = "Feature correlation matrix") -> go.Figure:
    c = num_df.dropna(axis=0, how="all").corr()
    labels = list(c.columns)
    z = np.round(c.values, 2)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=labels,
            y=labels,
            colorscale="RdBu_r",
            zmid=0,
            zmin=-1,
            zmax=1,
            colorbar=dict(title="ρ"),
            hovertemplate="%{y} vs %{x}<br>r=%{z}<extra></extra>",
        )
    )
    tall = len(labels)
    fontsize = max(8, min(11, int(420 / tall)))
    if tall <= 24:
        fig.update_traces(text=z, texttemplate="%{text}", textfont=dict(size=max(7, fontsize - 3)))
    fig.update_layout(title=title, height=min(980, max(560, tall * 16)), margin=dict(l=120, r=80, b=120, t=80))
    fig.update_xaxes(side="bottom", tickangle=-45)
    return fig


def fig_spot_futures(spot_daily: pd.DataFrame, fut_daily: pd.DataFrame, *, title: str) -> go.Figure:
    s_close = _series(spot_daily, "adj_close", "close").rename("spot")
    f_close = _series(fut_daily, "adj_close", "close").rename("future")
    comb = pd.concat([s_close, f_close], axis=1).dropna()
    spread = comb["spot"] - comb["future"]

    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=("Scatter: futures vs spot closes (aligned)", "Basis: spot − futures (USD)"),
        vertical_spacing=0.12,
    )
    rho = comb["future"].corr(comb["spot"])
    fig.add_trace(
        go.Scattergl(
            x=comb["future"],
            y=comb["spot"],
            mode="markers",
            marker=dict(color="rgba(31,119,180,0.35)", size=6),
            name="days",
        ),
        row=1,
        col=1,
    )
    m, b = np.polyfit(comb["future"].values, comb["spot"].values, 1)
    xf = np.linspace(comb["future"].min(), comb["future"].max(), 120)
    fig.add_trace(
        go.Scatter(
            x=xf,
            y=m * xf + b,
            mode="lines",
            line=dict(color="firebrick"),
            name=f"OLS (ρ≈{rho:.3f})",
        ),
        row=1,
        col=1,
    )
    fig.update_xaxes(title_text="BTC=F close (USD)", row=1, col=1)
    fig.update_yaxes(title_text="BTC-USD spot close (USD)", row=1, col=1)

    fig.add_trace(
        go.Scatter(x=spread.index, y=spread, mode="lines", line=dict(color="#8c564b"), name="basis"),
        row=2,
        col=1,
    )
    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_yaxes(title_text="USD", row=2, col=1)
    fig.update_layout(height=700, title_text=title, showlegend=True)
    return fig


def run_bitcoin_eda(
    *,
    daily_period: str = "2y",
    hourly_period: str = "729d",
    vol_window: int = 30,
    acf_max_lag: int = 50,
    output_dir: str | Path = "eda_output",
    write_html: bool = True,
) -> Dict[str, object]:
    """
    Run full EDA pipeline and optionally write HTML figures.

    Returns a dict with keys: ``paths`` (HTML paths), ``figures`` (plotly figures),
    ``feature_frame`` (numeric DataFrame used for correlation), ``metadata`` (notes).
    """
    out_path = Path(output_dir)
    if write_html:
        out_path.mkdir(parents=True, exist_ok=True)

    spot_d = fetch_yfinance_ohlcv(SPOT_TICKER, period=daily_period)
    fut_d = fetch_yfinance_ohlcv(FUT_TICKER, period=daily_period)
    hourly_raw = fetch_yfinance_ohlcv(
        SPOT_TICKER,
        period=hourly_period,
        interval="1h",
        allow_empty=True,
    )

    meta: Dict[str, object] = {
        "daily_rows_spot": len(spot_d),
        "daily_rows_future": len(fut_d),
        "hourly_rows": len(hourly_raw),
        "hourly_timezone_note": (
            "Interpret hour-of-day as the hour on the timestamps Yahoo returns "
            "(often naive); use for exploratory seasonality only."
        ),
    }

    feats = build_feature_frame(spot_d)

    figs = {
        "01_price_returns_vol": fig_price_returns_vol(spot_d, vol_window=vol_window),
        "02_autocorr_returns": fig_autocorr(spot_d, max_lag=acf_max_lag),
        "03_calendar": fig_calendar_effects(spot_d, hourly_raw),
        "04_corr_heatmap": fig_correlation_heatmap(feats),
        "05_spot_futures": fig_spot_futures(
            spot_d,
            fut_d,
            title="Spot BTC-USD vs BTC=F — level & basis",
        ),
    }

    paths: Dict[str, Path] = {}
    if write_html:
        for key, fig in figs.items():
            p = out_path / f"{key}.html"
            fig.write_html(p, include_plotlyjs="cdn")
            paths[key] = p

    return {
        "paths": paths,
        "figures": figs,
        "feature_frame": feats,
        "metadata": meta,
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Bitcoin EDA with Plotly HTML exports.")
    parser.add_argument("--output", default="eda_output", help="Directory for HTML files.")
    parser.add_argument("--period", default="2y", help="Daily history window ( Yahoo period string ).")
    parser.add_argument(
        "--hourly-period",
        default="729d",
        help="Hourly spot history (Yahoo cap).",
    )
    args = parser.parse_args(argv)

    res = run_bitcoin_eda(
        daily_period=args.period,
        hourly_period=args.hourly_period,
        output_dir=args.output,
        write_html=True,
    )

    meta = res["metadata"]
    print("EDA complete.")
    print(f"Daily spot bars: {meta['daily_rows_spot']} | Futures: {meta['daily_rows_future']} | Hourly: {meta['hourly_rows']}")
    for key, path in sorted(res["paths"].items()):
        print(f"  {key}: file://{path.resolve()}")

    feats: pd.DataFrame = res["feature_frame"]  # type: ignore[assignment]
    print(f"\nCorrelation matrix built from {feats.shape[1]} numeric features ({feats.shape[0]} rows).")


if __name__ == "__main__":
    main()
