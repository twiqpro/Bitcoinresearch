#!/usr/bin/env python3
"""
Export a single JSON bundle for `btc-dashboard` (Tailwind UI).

Uses **one** RF fit via `rf_backtest_predictions_table`, then the same simulator
functions as `bitcoin_backtest` so metrics and feature importances match.

Writes::
  btc-dashboard/public/dashboard.json

Run::

    .venv/bin/python export_dashboard_data.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "btc-dashboard" / "public"


def _total_return_frac(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def _max_dd_frac(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    roll = equity.cummax()
    return float((equity / roll - 1.0).min())


def _sharpe_daily(equity: pd.Series, periods: float = 365.0) -> float | None:
    r = equity.astype(float).pct_change().dropna()
    if len(r) < 2 or float(r.std(ddof=1)) <= 1e-12:
        return None
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods))


def main() -> None:
    from bitcoin_backtest import (
        build_long_stints_table,
        simulate_equity_buy_hold,
        simulate_equity_strategy,
    )
    from bitcoin_rf_next_close import rf_backtest_predictions_table

    PUBLIC.mkdir(parents=True, exist_ok=True)

    fee = 0.001
    bt, pipe, level_target = rf_backtest_predictions_table(include_ohlc=False)

    eq_s = simulate_equity_strategy(bt, fee)
    eq_bh = simulate_equity_buy_hold(bt, fee)
    stints = build_long_stints_table(bt)

    es = eq_s.astype(float) / float(eq_s.iloc[0])
    eb = eq_bh.astype(float) / float(eq_bh.iloc[0])
    equity_curve = [
        {"date": str(d)[:10], "strategy": float(es.loc[d]), "buy_hold": float(eb.loc[d])}
        for d in es.index.intersection(eb.index).sort_values()
    ]

    pred_df = bt.reset_index()
    predictions = [
        {
            "signal_date": str(r["signal_date"])[:10],
            "close_t": float(r["close_t"]),
            "pred_next_close": float(r["pred_next_close"]),
            "actual_next_close": float(r["actual_next_close"]),
        }
        for _, r in pred_df.iterrows()
    ]

    rf_model = pipe.named_steps["rf"]
    feats_arr = rf_model.feature_importances_
    try:
        name_arr = rf_model.feature_names_in_
    except AttributeError:
        name_arr = np.array([f"f{i}" for i in range(len(feats_arr))], dtype=object)

    paired = [{"feature": str(f), "importance": float(i)} for f, i in zip(name_arr, feats_arr)]
    paired.sort(key=lambda x: x["importance"], reverse=True)
    importance = paired[:20]

    wr = (
        float(stints["stint_profitable_vs_cash_before_fees"].astype(bool).mean())
        if len(stints) and "stint_profitable_vs_cash_before_fees" in stints.columns
        else None
    )

    stint_records = []
    for _, row in stints.iterrows():
        stint_records.append(
            {
                "entry_signal_date": str(row["entry_signal_date"])[:10],
                "exit_signal_date": str(row["exit_signal_date"])[:10],
                "nights_long": int(row["nights_long"]),
                "compounded_overnight_gross": float(row["compounded_overnight_gross"]),
                "holding_simple_return_frac": float(row["holding_simple_return_frac"]),
                "stint_profitable_vs_cash_before_fees": bool(row["stint_profitable_vs_cash_before_fees"]),
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fee": fee,
        "model_mode": "OHLC + level target" if level_target else "Indicators + log-return RF",
        "metrics": {
            "total_return_strategy_pct": _total_return_frac(eq_s) * 100,
            "total_return_bh_pct": _total_return_frac(eq_bh) * 100,
            "sharpe_strategy": _sharpe_daily(eq_s),
            "sharpe_bh": _sharpe_daily(eq_bh),
            "max_dd_strategy_pct": _max_dd_frac(eq_s) * 100,
            "max_dd_bh_pct": _max_dd_frac(eq_bh) * 100,
            "win_rate_stints_pct": (wr * 100) if wr is not None else None,
            "n_stints": int(len(stints)),
            "n_overnight_rows": int(len(bt)),
        },
        "equity_curve": equity_curve,
        "predictions": predictions,
        "trade_stints": stint_records,
        "feature_importance": importance,
    }

    out = PUBLIC / "dashboard.json"
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)

    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
