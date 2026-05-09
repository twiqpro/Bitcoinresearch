#!/usr/bin/env python3
"""
Backtest RF-driven BTC spot strategy on **2024** with transaction costs.

- **Signals:** Random Forest fitted on **2022–2023**, predictions on **2024**
  (`rf_backtest_predictions_table`).
- **Rule (long-only):** after each day's close ``t``, hold BTC overnight ``t→t+1`` iff
  ``pred_next_close > close_t``, else flat (cash earns 0).
- **Costs:** multiply equity by ``(1 - fee)`` whenever exposure **changes** (0.1% default
  per turnover → entry and exit each pay).
- **Benchmark:** fully long BTC from the first overnight in the panel, paying one-way
  entry fee, same marks.

Writes HTML (equity + metrics table) and CSV of inferred long stints.

Usage::

    python bitcoin_backtest.py --output backtest_output
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bitcoin_rf_next_close import rf_backtest_predictions_table

FEE_DEFAULT = 0.001


def _overnight_returns(bt: pd.DataFrame) -> np.ndarray:
    c = bt["close_t"].astype(float).values
    nxt = bt["actual_next_close"].astype(float).values
    return nxt / c


def simulate_equity_strategy(bt: pd.DataFrame, fee: float) -> pd.Series:
    pos = False
    E = 1.0
    pts: List[Tuple[pd.Timestamp, float]] = []
    rets = _overnight_returns(bt)
    for i, (_, row) in enumerate(bt.iterrows()):
        vd = pd.Timestamp(row["valuation_date"])
        pred = float(row["pred_next_close"])
        ct = float(row["close_t"])
        want = pred > ct

        if want != pos:
            E *= 1.0 - fee

        E *= rets[i] if want else 1.0
        pos = want
        pts.append((vd, E))

    ser = pd.Series({d: v for d, v in pts}).sort_index()
    return ser[~ser.index.duplicated(keep="last")]


def simulate_equity_buy_hold(bt: pd.DataFrame, fee: float) -> pd.Series:
    E = 1.0 - fee
    pts: List[Tuple[pd.Timestamp, float]] = []
    rets = _overnight_returns(bt)
    for i, (_, row) in enumerate(bt.iterrows()):
        vd = pd.Timestamp(row["valuation_date"])
        E *= rets[i]
        pts.append((vd, E))
    ser = pd.Series({d: v for d, v in pts}).sort_index()
    return ser[~ser.index.duplicated(keep="last")]


def build_long_stints_table(bt: pd.DataFrame) -> pd.DataFrame:
    """
    Contiguous intervals where signal is **long**. Each stint's compounded gross BTC
    return ignores intra-stint turnover fees but records entry/exit for audit.
    Strategy P&L differs because fees hit on toggles (`simulate_equity_strategy`).
    """
    want = (bt["pred_next_close"].astype(float) > bt["close_t"].astype(float)).values

    rows_out: List[Dict[str, object]] = []
    prev_w = False
    start_idx: Optional[int] = None

    for idx in range(len(bt)):
        w = bool(want[idx])
        if w and not prev_w:
            start_idx = idx
        if not w and prev_w and start_idx is not None:
            sl = bt.iloc[start_idx:idx]
            rvec = sl["actual_next_close"].astype(float).values / sl["close_t"].astype(float).values
            gross = float(np.prod(rvec))
            rows_out.append(
                {
                    "entry_signal_date": bt.index[start_idx],
                    "exit_signal_date": bt.index[idx],
                    "nights_long": len(sl),
                    "entry_close_usd": float(sl.iloc[0]["close_t"]),
                    "signal_exit_close_usd": float(bt.iloc[idx]["close_t"]),
                    "compounded_overnight_gross": gross,
                    "holding_simple_return_frac": gross - 1.0,
                    "stint_profitable_vs_cash_before_fees": gross > 1.0,
                }
            )
            start_idx = None
        prev_w = w

    if prev_w and start_idx is not None:
        sl = bt.iloc[start_idx:]
        rvec = sl["actual_next_close"].astype(float).values / sl["close_t"].astype(float).values
        gross = float(np.prod(rvec))
        rows_out.append(
            {
                "entry_signal_date": bt.index[start_idx],
                "exit_signal_date": bt.index[-1],
                "nights_long": len(sl),
                "entry_close_usd": float(sl.iloc[0]["close_t"]),
                "signal_exit_close_usd": float(bt.iloc[-1]["close_t"]),
                "compounded_overnight_gross": gross,
                "holding_simple_return_frac": gross - 1.0,
                "stint_profitable_vs_cash_before_fees": gross > 1.0,
                "note": "still_long_last_row",
            }
        )

    return pd.DataFrame(rows_out)


def total_return_frac(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def max_drawdown_frac(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    roll = equity.cummax()
    dd = equity / roll - 1.0
    return float(dd.min())


def sharpe_daily(equity: pd.Series, periods_per_year: float = 365.0) -> float:
    r = equity.astype(float).pct_change().dropna()
    if len(r) < 2 or float(r.std(ddof=1)) <= 1e-12:
        return float("nan")
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year))


def rebase_equity(series: pd.Series) -> pd.Series:
    """Normalize so first observation = 1.0 (readable overlay)."""
    if series.empty:
        return series
    return series.astype(float) / float(series.iloc[0])


def build_report_figure(
    strat: pd.Series,
    bh: pd.Series,
    metrics: pd.DataFrame,
    title: str,
    stint_df: Optional[pd.DataFrame] = None,
) -> go.Figure:
    row_heights = [0.48, 0.20, 0.30] if stint_df is not None and len(stint_df) else [0.58, 0.40]
    titles = (
        ("Equity (rebased to 1 at first mark)", "Summary metrics", "Long stints (gross overnight vs cash)")
        if len(row_heights) == 3
        else ("Equity (rebased to 1 at first mark)", "Summary metrics")
    )
    specs = [[{"type": "scatter"}], [{"type": "table"}]]
    if len(row_heights) == 3:
        specs.append([{"type": "table"}])

    fig = make_subplots(
        rows=len(row_heights),
        cols=1,
        row_heights=row_heights,
        vertical_spacing=0.06,
        subplot_titles=titles,
        specs=specs,
    )
    rs = rebase_equity(strat)
    rb = rebase_equity(bh)
    fig.add_trace(
        go.Scatter(
            x=rs.index,
            y=rs.values,
            name="RF signal strategy",
            line=dict(color="#e6550d", width=2),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=rb.index,
            y=rb.values,
            name="Buy & hold",
            line=dict(color="#31a354", width=2),
        ),
        row=1,
        col=1,
    )
    fig.update_yaxes(title_text="Equity", row=1, col=1)
    fig.update_xaxes(title_text="Mark date (after overnight)", row=1, col=1)

    r_table = 2
    fig.add_trace(
        go.Table(
            header=dict(values=list(metrics.columns), fill_color="#f0f0f0", font=dict(size=12)),
            cells=dict(
                values=[metrics[c].astype(str).tolist() for c in metrics.columns],
                align="left",
                font=dict(size=11),
                height=28,
            ),
        ),
        row=r_table,
        col=1,
    )
    if stint_df is not None and len(stint_df):
        disp = stint_df.copy()
        for c in ("compounded_overnight_gross", "holding_simple_return_frac", "entry_close_usd", "signal_exit_close_usd"):
            if c in disp.columns:
                disp[c] = disp[c].map(lambda x: f"{float(x):.4f}" if pd.notna(x) else "")
        cols = [
            c
            for c in (
                "entry_signal_date",
                "exit_signal_date",
                "nights_long",
                "compounded_overnight_gross",
                "holding_simple_return_frac",
                "stint_profitable_vs_cash_before_fees",
            )
            if c in disp.columns
        ]
        fig.add_trace(
            go.Table(
                columnwidth=[120, 120, 60, 100, 80, 140],
                header=dict(values=cols, fill_color="#e8e8e8", font=dict(size=11)),
                cells=dict(
                    values=[disp[c].astype(str).tolist() for c in cols],
                    align="left",
                    font=dict(size=10),
                    height=24,
                ),
            ),
            row=3,
            col=1,
        )
    fig.update_layout(title=title, height=1080 if len(row_heights) == 3 else 820, showlegend=True)
    return fig


def run_backtest(
    *,
    fee: float = FEE_DEFAULT,
    history_start: str = "2020-01-01",
    include_ohlc: bool = False,
    output_dir: Union[str, Path] = "backtest_output",
) -> Dict[str, object]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    bt, _pipe, level_target = rf_backtest_predictions_table(
        history_start=history_start,
        include_ohlc=include_ohlc,
    )

    eq_s = simulate_equity_strategy(bt, fee)
    eq_bh = simulate_equity_buy_hold(bt, fee)

    stint_df = build_long_stints_table(bt)
    stint_df_path = out / "trade_stints.csv"
    stint_df.to_csv(stint_df_path, index=False)

    wr = (
        float(stint_df["stint_profitable_vs_cash_before_fees"].astype(bool).mean())
        if len(stint_df) and "stint_profitable_vs_cash_before_fees" in stint_df.columns
        else float("nan")
    )

    mode = "OHLC + level target" if level_target else "Indicators only (log-return RF)"

    metrics = pd.DataFrame(
        [
            {
                "Metric": "Total return",
                "RF_strategy": f"{total_return_frac(eq_s)*100:.2f}%",
                "Buy_hold": f"{total_return_frac(eq_bh)*100:.2f}%",
            },
            {
                "Metric": "Sharpe (daily, ×√365)",
                "RF_strategy": f"{sharpe_daily(eq_s):.3f}",
                "Buy_hold": f"{sharpe_daily(eq_bh):.3f}",
            },
            {
                "Metric": "Max drawdown",
                "RF_strategy": f"{max_drawdown_frac(eq_s)*100:.2f}%",
                "Buy_hold": f"{max_drawdown_frac(eq_bh)*100:.2f}%",
            },
            {
                "Metric": "Win rate — long stints (gross>1 vs cash)",
                "RF_strategy": f"{wr*100:.1f}%" if np.isfinite(wr) else "n/a",
                "Buy_hold": "—",
            },
            {
                "Metric": "# long stints (entries)",
                "RF_strategy": str(len(stint_df)),
                "Buy_hold": "—",
            },
            {
                "Metric": "Turnover fee",
                "RF_strategy": f"{fee*100:.2g}% each switch",
                "Buy_hold": f"{fee*100:.2g}% one-way entry",
            },
            {"Metric": "RF spec", "RF_strategy": mode, "Buy_hold": "—"},
            {"Metric": "2024 overnight rows", "RF_strategy": str(len(bt)), "Buy_hold": str(len(bt))},
        ]
    )

    ttl = (
        "BTC RF long/flat overnight backtest vs buy&hold<br>"
        f"<sup>{mode}; costs {fee*100:.2f}% per turnover; train 2022–23, sim 2024</sup>"
    )
    fig = build_report_figure(eq_s, eq_bh, metrics, ttl, stint_df=stint_df)
    report_path = out / "equity_curve_and_metrics.html"
    fig.write_html(report_path, include_plotlyjs="cdn")

    return {
        "bt_panel": bt,
        "equity_strategy": eq_s,
        "equity_bh": eq_bh,
        "stints": stint_df,
        "metrics": metrics,
        "paths": {"report": report_path, "trades_csv": stint_df_path},
        "level_target": level_target,
        "fee": fee,
        "win_rate_stints_gross": wr,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backtest RF BTC overnight strategy.")
    p.add_argument("--output", default="backtest_output", help="Directory for HTML/CSV.")
    p.add_argument("--fee", type=float, default=FEE_DEFAULT, help="Fractional cost per turnover (default 0.001).")
    p.add_argument("--history-start", default="2020-01-01", help="Warm-up window for Yahoo download.")
    p.add_argument(
        "--include-ohlc",
        action="store_true",
        help="Use RF variant with OHLC features + level targets ( brittle OOS).",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    res = run_backtest(
        fee=args.fee,
        history_start=args.history_start,
        include_ohlc=args.include_ohlc,
        output_dir=args.output,
    )
    print("Backtest complete (2024 panel).")
    print(res["metrics"].to_string(index=False))
    print(f"\nTrade stint log: {res['paths']['trades_csv'].resolve()}")
    print(f"HTML report:     {res['paths']['report'].resolve()}")
    print(
        "\nNote: stint 'win rate' compares gross compounded BTC overnight vs cash **before** "
        "subtracting turnover fees applied in the stepped equity simulator."
    )


if __name__ == "__main__":
    main()
