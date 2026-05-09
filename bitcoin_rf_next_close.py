#!/usr/bin/env python3
"""
Random Forest to predict **Bitcoin's next-day close**.

Default setup matches *“technical indicators as features”*: **OHLC / Adj Close columns
are dropped** from ``X``, the model fits **next-day log return**
:math:`\\ln(C_{t+1}/C_t)`, then **reconstructs** :math:`\\hat C_{t+1}=C_t\\,e^{\\hat r}` for
USD metrics and plotting. This avoids the failure mode where trees trained on 2022–2023
levels extrapolate badly into a different 2024 regime.

Optional ``--include-ohlc`` keeps Open/High/Low/Close/Adj Close in ``X`` and regresses
**level** next close directly (often dominated by ``Close`` / brittle OOS).

- **Train:** feature dates in **2022–2023** (history from ``--history-start`` for SMA warm-up).
- **Test:** feature dates in **2024**.
- **Pipeline:** ``StandardScaler`` + ``RandomForestRegressor`` (fit scaler on train only).

Usage::

    python bitcoin_rf_next_close.py --output rf_output
    python bitcoin_rf_next_close.py --output rf_output --include-ohlc   # level features + level target
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from bitcoin_technicals import add_technical_indicators
from btc_spot_futures_download import fetch_yfinance_ohlcv

SPOT = "BTC-USD"
TRAIN_YEARS = frozenset({2022, 2023})
TEST_YEAR = 2024

LEVEL_NAMES = frozenset({"open", "high", "low", "close", "adj close"})


def _col_ci(df: pd.DataFrame, *cands: str) -> str:
    cmap = {str(c).strip().lower(): c for c in df.columns}
    for c in cands:
        k = c.strip().lower()
        if k in cmap:
            return cmap[k]
    raise KeyError(f"None of {cands} found in {df.columns.tolist()}")


def build_dataset(
    *,
    history_start: str = "2020-01-01",
    include_ohlc: bool = False,
) -> Tuple[pd.DataFrame, List[str], bool]:
    """Return modeling frame with columns: features + ``y`` + ``close_t`` + ``next_close``."""
    spot = fetch_yfinance_ohlcv(SPOT, start=history_start, period=None)
    feat = add_technical_indicators(spot)
    cc = _col_ci(feat, "close", "adj close")
    close = pd.to_numeric(feat[cc], errors="coerce")

    X_full = feat.select_dtypes(include=[np.number]).copy()
    if include_ohlc:
        X = X_full
        y_level = close.shift(-1)
        frame = pd.concat(
            [
                X,
                y_level.rename("y"),
                close.rename("close_t"),
                close.shift(-1).rename("next_close"),
            ],
            axis=1,
        ).dropna()
        feature_cols = X.columns.tolist()
        return frame, feature_cols, True

    drop_cols = [c for c in X_full.columns if str(c).strip().lower() in LEVEL_NAMES]
    X = X_full.drop(columns=drop_cols, errors="ignore")
    y = np.log(close.shift(-1) / close)
    frame = pd.concat(
        [
            X,
            y.rename("y"),
            close.rename("close_t"),
            close.shift(-1).rename("next_close"),
        ],
        axis=1,
    ).dropna()
    feature_cols = X.columns.tolist()
    return frame, feature_cols, False


def time_split_mask(idx: pd.DatetimeIndex) -> Tuple[np.ndarray, np.ndarray]:
    years = pd.Series(idx).dt.year.to_numpy()
    train_m = np.isin(years, list(TRAIN_YEARS))
    test_m = years == TEST_YEAR
    return train_m, test_m


def make_rf_pipeline(
    *,
    n_estimators: int = 400,
    max_depth: Optional[int] = 18,
    min_samples_leaf: int = 2,
    random_state: int = 42,
) -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "rf",
                RandomForestRegressor(
                    n_estimators=n_estimators,
                    max_depth=max_depth,
                    min_samples_leaf=min_samples_leaf,
                    random_state=random_state,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def rf_backtest_predictions_table(
    *,
    history_start: str = "2020-01-01",
    include_ohlc: bool = False,
    n_estimators: int = 400,
    max_depth: Optional[int] = 18,
    min_samples_leaf: int = 2,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, Pipeline, bool]:
    """
    Train on 2022–2023, return **2024** rows for path-dependent backtests.

    Each row is a **signal date** ``t`` (index): features known at ``t`` produce a
    forecast of the **next** close; ``close_t`` is the spot close at ``t``;
    ``actual_next_close`` is the realized close on **t+1 calendar day** (labels
    ``valuation_date``).
    """
    frame, feature_cols, level_target = build_dataset(
        history_start=history_start,
        include_ohlc=include_ohlc,
    )
    idx_all = pd.DatetimeIndex(frame.index)
    train_m, test_m = time_split_mask(idx_all)

    X_train = frame.loc[train_m, feature_cols]
    X_test = frame.loc[test_m, feature_cols]
    y_train = frame.loc[train_m, "y"]
    close_t_test = frame.loc[test_m, "close_t"].values.astype(float)
    next_close_test = frame.loc[test_m, "next_close"].values.astype(float)

    if len(X_train) == 0 or len(X_test) == 0:
        raise RuntimeError("Insufficient 2024 / train data for RF backtest table.")

    pipe = make_rf_pipeline(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=random_state,
    )
    pipe.fit(X_train, y_train)
    pred_raw = pipe.predict(X_test)

    if level_target:
        pred_close = pred_raw.astype(float)
    else:
        pred_close = close_t_test * np.exp(pred_raw.astype(float))

    sig_idx = idx_all[test_m]
    valuation_date = sig_idx + pd.Timedelta(days=1)

    bt = pd.DataFrame(
        {
            "close_t": close_t_test,
            "pred_next_close": pred_close,
            "actual_next_close": next_close_test,
            "valuation_date": valuation_date,
        },
        index=sig_idx,
    )
    bt.index.name = "signal_date"
    bt.sort_index(inplace=True)

    # Optional: realised overnight return when long BTC t → t+1
    bt["overnight_simple_ret"] = bt["actual_next_close"] / bt["close_t"] - 1.0
    bt["signal_long"] = bt["pred_next_close"] > bt["close_t"]
    bt["forecast_ret"] = bt["pred_next_close"] / bt["close_t"] - 1.0

    return bt, pipe, level_target


def baseline_persistence_rmse(actual: np.ndarray, same_day_close: np.ndarray) -> float:
    return float(np.sqrt(mean_squared_error(actual, same_day_close)))


def run_rf_next_close(
    *,
    history_start: str = "2020-01-01",
    include_ohlc: bool = False,
    rf_n_estimators: int = 400,
    rf_max_depth: Optional[int] = 18,
    rf_min_samples_leaf: int = 2,
    random_state: int = 42,
    output_dir: Union[str, Path] = "rf_output",
) -> dict:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frame, feature_cols, level_target = build_dataset(
        history_start=history_start,
        include_ohlc=include_ohlc,
    )

    idx = pd.DatetimeIndex(frame.index)
    train_m, test_m = time_split_mask(idx)

    X_train = frame.loc[train_m, feature_cols]
    X_test = frame.loc[test_m, feature_cols]
    y_train = frame.loc[train_m, "y"]
    y_test_model = frame.loc[test_m, "y"]
    close_t_test = frame.loc[test_m, "close_t"].values.astype(float)
    next_close_test = frame.loc[test_m, "next_close"].values.astype(float)

    if len(X_train) == 0 or len(X_test) == 0:
        raise RuntimeError(
            f"Insufficient split: train n={len(X_train)}, test n={len(X_test)}. "
            "Check Yahoo BTC-USD coverage for 2022–2024."
        )

    pipe = make_rf_pipeline(
        n_estimators=rf_n_estimators,
        max_depth=rf_max_depth,
        min_samples_leaf=rf_min_samples_leaf,
        random_state=random_state,
    )
    pipe.fit(X_train, y_train)
    pred_model = pipe.predict(X_test)

    if level_target:
        pred_close = pred_model
        y_actual_usd = next_close_test
        rmse_usd = float(np.sqrt(mean_squared_error(y_actual_usd, pred_close)))
        mae_usd = float(mean_absolute_error(y_actual_usd, pred_close))
        r2_usd = float(r2_score(y_actual_usd, pred_close))
        rmse_log = np.nan
        r2_log = np.nan
    else:
        pred_close = close_t_test * np.exp(pred_model)
        y_actual_usd = next_close_test
        rmse_usd = float(np.sqrt(mean_squared_error(y_actual_usd, pred_close)))
        mae_usd = float(mean_absolute_error(y_actual_usd, pred_close))
        r2_usd = float(r2_score(y_actual_usd, pred_close))
        rmse_log = float(np.sqrt(mean_squared_error(y_test_model.values, pred_model)))
        r2_log = float(r2_score(y_test_model.values, pred_model))

    base_rmse = baseline_persistence_rmse(y_actual_usd, close_t_test)

    rf_model = pipe.named_steps["rf"]
    importances = pd.Series(rf_model.feature_importances_, index=feature_cols).sort_values(ascending=False)

    ts = idx[test_m]
    fig_main = go.Figure()
    fig_main.add_trace(
        go.Scatter(x=ts, y=y_actual_usd, name="Actual next close", line=dict(color="#333", width=1.5))
    )
    fig_main.add_trace(
        go.Scatter(x=ts, y=pred_close, name="RF prediction", line=dict(color="#e6550d", width=1.2))
    )
    fig_main.add_trace(
        go.Scatter(
            x=ts,
            y=close_t_test,
            name="Naive: close(t) as forecast",
            line=dict(color="#9e9ac8", width=1, dash="dot"),
        )
    )

    sub = (
        "Level target + OHLC features (--include-ohlc)"
        if level_target
        else "Indicators only; fitted on log returns, plotted in USD after reconstruction"
    )
    fig_main.update_layout(
        title=f"2024 test: next-day close — actual vs RF vs naive<br><sup>{sub}</sup>",
        xaxis_title="Feature date t (target is close on t+1)",
        yaxis_title="USD",
        height=540,
        legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="right", x=1),
    )
    main_path = out_dir / "predictions_vs_actual.html"
    fig_main.write_html(main_path, include_plotlyjs="cdn")

    top_k = importances.head(25)
    fig_imp = go.Figure(
        go.Bar(
            x=top_k.values[::-1],
            y=top_k.index[::-1],
            orientation="h",
            marker_color="#3182bd",
        )
    )
    fig_imp.update_layout(
        title="Random Forest feature importance (top 25)",
        xaxis_title="Importance",
        height=min(900, 120 + 22 * len(top_k)),
        margin=dict(l=160, r=40, t=60, b=50),
    )
    imp_path = out_dir / "feature_importance.html"
    fig_imp.write_html(imp_path, include_plotlyjs="cdn")

    return {
        "rmse_usd": rmse_usd,
        "mae_usd": mae_usd,
        "r2_usd": r2_usd,
        "rmse_log_return": rmse_log,
        "r2_log_return": r2_log,
        "baseline_rmse_usd": base_rmse,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "feature_importances": importances,
        "paths": {"predictions": main_path, "importance": imp_path},
        "pipeline": pipe,
        "level_target": level_target,
        "include_ohlc": include_ohlc,
    }


def trading_commentary(res: dict) -> str:
    ru, mu, r2u = res["rmse_usd"], res["mae_usd"], res["r2_usd"]
    rl, r2l = res["rmse_log_return"], res["r2_log_return"]
    br = res["baseline_rmse_usd"]
    mode = "level target + OHLC/A features" if res["level_target"] else "log-return target, indicators only"
    lines: List[str] = [
        "How to read this for trading (not investment advice):",
        "",
        f"- **Model mode:** {mode}.",
        f"- **USD test error:** RMSE ≈ ${ru:,.0f}, MAE ≈ ${mu:,.0f}; **R² on closes** ≈ {r2u:.3f}. "
        "**High R² on prices** often reflects that **today** and **tomorrow’s** closes move together "
        "(random-walk-ish levels); it does **not** prove profitable **return** forecasting.",
        f"- **Naïve persistence** (forecast tomorrow = today’s close): RMSE ≈ ${br:,.0f}. "
        f"({'RF beats naive on RMSE ✓' if ru < br * 0.99 else 'RF does **not** beat naive on RMSE ✗'}) — "
        "close-level accuracy must beat this hurdle **after** spreads and latency.",
    ]
    if np.isfinite(rl):
        lines.append(
            f"- **Log-return fit:** test RMSE ≈ **{rl:.6f}** in **daily log-return** units; R²(log ret) ≈ **{r2l:.3f}**. "
            "**Negative R²** means the forest is **worse** than predicting each day’s train-set mean log return "
            "on this 2024 slice — i.e., no usable linear explanatory power."
        )
    lines.extend(
        [
            "- **Importances** show which features the forest split on most often — not causal effects "
            "and correlated with other drivers.",
            "- **Regime drift:** training on 2022–2023 vs testing 2024 can change volatility and trend; "
            "walk-forward retraining reduces illusion of stability.",
            "- **Trading:** profitable strategies need **edge vs benchmark + costs** on **returns or "
            "signals**, not only low RMSE on nominal prices.",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RF next-close model for BTC-USD.")
    p.add_argument("--output", default="rf_output", help="Directory for HTML exports.")
    p.add_argument(
        "--history-start",
        default="2020-01-01",
        help="Download start date for indicator warmup (before 2022).",
    )
    p.add_argument(
        "--include-ohlc",
        action="store_true",
        help="Include Open/High/Low/Close/Adj Close as features and regress next close in USD directly.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    res = run_rf_next_close(
        history_start=args.history_start,
        output_dir=args.output,
        include_ohlc=args.include_ohlc,
    )

    print(
        "Random Forest → next-day close "
        f"(train 2022–2023, test 2024){' [OHLC features + level target]' if res['include_ohlc'] else ''}"
    )
    print(f"Train rows: {res['n_train']} | Test rows: {res['n_test']}")
    print(f"RMSE (USD):   {res['rmse_usd']:,.2f}")
    print(f"MAE (USD):    {res['mae_usd']:,.2f}")
    print(f"R² (closes):  {res['r2_usd']:,.4f}")
    if np.isfinite(res["rmse_log_return"]):
        print(f"RMSE (log-ret): {res['rmse_log_return']:.6f} | R² (log-ret): {res['r2_log_return']:,.4f}")
    print(f"Naive persistence RMSE (USD): {res['baseline_rmse_usd']:,.2f}")
    print("\nTop feature importances:")
    print(res["feature_importances"].head(15).to_string())
    print(f"\nWrote HTML:\n  {res['paths']['predictions'].resolve()}\n  {res['paths']['importance'].resolve()}")
    print("\n" + trading_commentary(res))


if __name__ == "__main__":
    main()
