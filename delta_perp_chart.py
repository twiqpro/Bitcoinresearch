#!/usr/bin/env python3
"""
Delta Exchange — BTCUSD / ETHUSD perpetual futures only.

  - history: REST ``/v2/history/candles``; saves CSV + PNG under ``delta_data/`` by default.
  - live: WebSocket ``ticker`` on ``wss://public-socket.india.delta.exchange`` (~5s).

Deps: pip install requests websocket-client matplotlib
      optional: pip install python-dotenv

Examples:
  Put secrets in ``config/.env`` or project-root ``.env`` (ignored by git).
  export DELTA_API_KEY="..."   # optional; candles are public but key is sent if set
  .venv/bin/python delta_perp_chart.py history --hours 72 --resolution 5m
  .venv/bin/python delta_perp_chart.py history --replay --output-dir delta_data
  .venv/bin/python delta_perp_chart.py live

Env: DELTA_REST_BASE, DELTA_WS_URL, DELTA_API_KEY (see delta_exchange/).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import websocket

from delta_exchange.candles_csv import (
    candle_rows_from_file,
    write_candles_csv,
    write_fetch_meta,
)
from delta_exchange.constants import PERP_SYMBOLS, ws_public_url
from delta_exchange.history import fetch_candles_asc
from delta_exchange.session import build_rest_session


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        root = _project_root()
        load_dotenv(root / ".env")
        load_dotenv(root / "config" / ".env")
    except ImportError:
        pass


def _figure_history(symbol_rows: dict[str, list[dict[str, Any]]], resolution: str):
    fig, axes = plt.subplots(len(PERP_SYMBOLS), 1, figsize=(11, 7), sharex=True)
    if len(PERP_SYMBOLS) == 1:
        axes = [axes]
    for ax, sym in zip(axes, PERP_SYMBOLS):
        rows = symbol_rows.get(sym) or []
        if not rows:
            ax.set_title(f"{sym} — no data")
            continue
        times = [
            datetime.fromtimestamp(int(r["time"]), tz=timezone.utc) for r in rows
        ]
        closes = [float(r["close"]) for r in rows]
        ax.plot(
            times,
            closes,
            color="#f7931a" if sym == "BTCUSD" else "#627eea",
            lw=0.9,
        )
        ax.set_ylabel("close")
        ax.set_title(f"{sym} — {resolution}")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%m-%d %H:%M", tz=timezone.utc)
        )

    axes[-1].set_xlabel("UTC")
    fig.suptitle(
        "Delta perpetual futures — historical close (/v2/history/candles)"
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def _history_csv_name(symbol: str, resolution: str, start: int, end: int) -> str:
    return f"{symbol}_{resolution}_{start}_{end}.csv"


def run_history_fetch(
    *,
    resolution: str,
    start: int,
    end: int,
    output_dir: Path,
    save_csv: bool,
    chart_file: Path,
    show: bool,
) -> None:
    sess = build_rest_session()
    symbol_rows: dict[str, list[dict[str, Any]]] = {}
    csv_map: dict[str, str] = {}

    for sym in PERP_SYMBOLS:
        rows = fetch_candles_asc(sym, resolution, start, end, session=sess)
        symbol_rows[sym] = rows
        if save_csv and rows:
            name = _history_csv_name(sym, resolution, start, end)
            p = output_dir / name
            write_candles_csv(p, rows)
            csv_map[sym] = name
            print(f"Wrote {p} ({len(rows)} rows)")

    if save_csv:
        write_fetch_meta(
            output_dir / "last_fetch.json",
            resolution=resolution,
            start=start,
            end=end,
            symbols=PERP_SYMBOLS,
            files=csv_map,
        )
        print(f"Wrote {output_dir / 'last_fetch.json'}")

    fig = _figure_history(symbol_rows, resolution)
    chart_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chart_file, dpi=150, bbox_inches="tight")
    print(f"Wrote {chart_file}")
    if show:
        plt.show()
    else:
        plt.close(fig)


def run_history_replay(*, output_dir: Path, chart_file: Path, show: bool) -> None:
    meta_path = output_dir / "last_fetch.json"
    if not meta_path.is_file():
        raise SystemExit(f"Missing {meta_path}; run `history` without --replay first.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    resolution = meta["resolution"]
    symbol_rows: dict[str, list[dict[str, Any]]] = {}
    for sym, fname in meta["csv_files"].items():
        path = output_dir / fname
        if not path.is_file():
            raise SystemExit(f"Missing CSV {path}")
        symbol_rows[sym] = candle_rows_from_file(path)
        print(f"Loaded {path} ({len(symbol_rows[sym])} rows)")

    fig = _figure_history(symbol_rows, resolution)
    chart_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chart_file, dpi=150, bbox_inches="tight")
    print(f"Wrote {chart_file}")
    if show:
        plt.show()
    else:
        plt.close(fig)


def _run_live(history_hours: float | None, resolution: str) -> None:
    lock = threading.Lock()
    maxlen = 900
    series: dict[str, deque[tuple[float, float]]] = {
        s: deque(maxlen=maxlen) for s in PERP_SYMBOLS
    }

    preload: dict[str, list[dict[str, Any]] | None] = {s: None for s in PERP_SYMBOLS}
    if history_hours and history_hours > 0:
        end = int(time.time())
        start = end - int(history_hours * 3600)
        sess = build_rest_session()
        for sym in PERP_SYMBOLS:
            try:
                preload[sym] = fetch_candles_asc(
                    sym, resolution, start, end, session=sess
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[history preload {sym}] {exc}")

    def on_message(ws: websocket.WebSocketApp, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if data.get("type") != "ticker":
            return
        ts_us = data.get("ts")
        if ts_us is None:
            return
        t_sec = float(ts_us) / 1e6
        for item in data.get("d") or []:
            sym = item.get("s")
            if sym not in series:
                continue
            mp = item.get("m")
            if mp is None:
                continue
            with lock:
                series[sym].append((t_sec, float(mp)))

    def on_open(ws: websocket.WebSocketApp) -> None:
        payload = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {"name": "ticker", "symbols": list(PERP_SYMBOLS)},
                ]
            },
        }
        ws.send(json.dumps(payload))
        print("Subscribed to public ticker:", list(PERP_SYMBOLS))

    url = ws_public_url()
    ws_app = websocket.WebSocketApp(url, on_message=on_message, on_open=on_open)

    def run_ws() -> None:
        ws_app.run_forever(ping_interval=25, ping_timeout=10)

    threading.Thread(target=run_ws, daemon=True).start()

    fig, axes = plt.subplots(len(PERP_SYMBOLS), 1, figsize=(11, 7), sharex=True)
    if len(PERP_SYMBOLS) == 1:
        axes = [axes]

    live_lines = []
    for ax, sym in zip(axes, PERP_SYMBOLS):
        color = "#f7931a" if sym == "BTCUSD" else "#627eea"
        rows = preload.get(sym) or []
        if rows:
            ts = [
                datetime.fromtimestamp(r["time"], tz=timezone.utc) for r in rows
            ]
            ys = [r["close"] for r in rows]
            ax.plot(ts, ys, color=color, lw=0.7, alpha=0.45, label="REST close")
        (l_ln,) = ax.plot([], [], color=color, lw=1.1, label="mark (live)")
        ax.legend(loc="upper left", fontsize="small")
        ax.set_ylabel("price")
        ax.set_title(sym)
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz=timezone.utc))
        live_lines.append((sym, l_ln))

    axes[-1].set_xlabel("UTC")
    title = (
        f"Delta perpetual — live mark price (WS ticker, ~5s) — {url}"
    )
    fig.suptitle(title)
    fig.tight_layout()

    plt.ion()
    try:
        while plt.fignum_exists(fig.number):
            with lock:
                snap = {
                    sym: list(series[sym]) for sym in PERP_SYMBOLS
                }
            for sym, ln in live_lines:
                pts = snap[sym]
                if not pts:
                    continue
                xs = [
                    datetime.fromtimestamp(t, tz=timezone.utc) for t, _ in pts
                ]
                ys = [p for _, p in pts]
                ln.set_data(xs, ys)
                ax_idx = PERP_SYMBOLS.index(sym)
                axes[ax_idx].relim()
                axes[ax_idx].autoscale_view()

            fig.autofmt_xdate()
            plt.pause(0.25)

    finally:
        ws_app.close()
        plt.ioff()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    ph = sub.add_parser(
        "history", help="Fetch past candles, save CSV + chart (BTCUSD & ETHUSD only)"
    )
    ph.add_argument("--resolution", default="5m", help="e.g. 1m 5m 1h")
    ph.add_argument(
        "--hours",
        type=float,
        default=48,
        help="How far back from now (ignored with --replay)",
    )
    ph.add_argument(
        "--output-dir",
        type=Path,
        default=Path("delta_data"),
        help="Where to write CSV files and last_fetch.json",
    )
    ph.add_argument(
        "--chart-file",
        type=Path,
        default=None,
        help="PNG path (default: <output-dir>/history_close_<resolution>.png)",
    )
    ph.add_argument(
        "--no-save-csv",
        action="store_true",
        help="Only plot and save PNG; do not write CSV",
    )
    ph.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open an interactive matplotlib window",
    )
    ph.add_argument(
        "--replay",
        action="store_true",
        help="Rebuild chart from CSV + last_fetch.json in output-dir (no API calls)",
    )

    pl = sub.add_parser("live", help="Live mark price chart (websocket ticker)")
    pl.add_argument(
        "--with-history-hours",
        type=float,
        default=0,
        metavar="H",
        help="If >0, underlay REST close for the last H hours before live stream",
    )
    pl.add_argument(
        "--history-resolution",
        default="5m",
        help="Resolution for optional --with-history-hours underlay",
    )

    _maybe_load_dotenv()
    args = p.parse_args()
    end = int(time.time())

    if args.cmd == "history":
        out_dir: Path = args.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        chart_file: Path = args.chart_file or (
            out_dir / f"history_close_{args.resolution}.png"
        )
        show = not args.no_show

        if args.replay:
            run_history_replay(
                output_dir=out_dir,
                chart_file=chart_file,
                show=show,
            )
        else:
            start = end - int(args.hours * 3600)
            run_history_fetch(
                resolution=args.resolution,
                start=start,
                end=end,
                output_dir=out_dir,
                save_csv=not args.no_save_csv,
                chart_file=chart_file,
                show=show,
            )
    else:
        h = getattr(args, "with_history_hours", 0)
        hres = getattr(args, "history_resolution", "5m")
        _run_live(h if h > 0 else None, hres)


if __name__ == "__main__":
    main()
