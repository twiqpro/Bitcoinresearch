#!/usr/bin/env python3
"""
Export Delta perpetual OHLC (BTCUSD / ETHUSD) for ``btc-dashboard``.

Writes ``btc-dashboard/public/delta_perp_candles.json`` (served as a static file).

Load ``config/.env`` if python-dotenv is installed. Optional ``DELTA_API_KEY``.

  .venv/bin/python export_delta_dashboard.py --hours 168 --resolution 5m
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "btc-dashboard" / "public"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / "config" / ".env")
    except ImportError:
        pass


def main() -> None:
    _load_dotenv()

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours", type=float, default=168, help="History depth (from now)")
    p.add_argument("--resolution", default="5m", help="e.g. 1m 5m 15m 1h")
    p.add_argument(
        "--output",
        type=Path,
        default=PUBLIC / "delta_perp_candles.json",
        help="Output JSON path",
    )
    args = p.parse_args()

    import time

    from delta_exchange.constants import PERP_SYMBOLS
    from delta_exchange.history import fetch_candles_asc
    from delta_exchange.session import build_rest_session

    end = int(time.time())
    start = end - int(args.hours * 3600)
    sess = build_rest_session()
    candles: dict[str, list[dict[str, float | int]]] = {}
    for sym in PERP_SYMBOLS:
        rows = fetch_candles_asc(sym, args.resolution, start, end, session=sess)
        candles[sym] = [
            {
                "time": int(r["time"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
            }
            for r in rows
        ]
        print(f"{sym}: {len(candles[sym])} candles")

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolution": args.resolution,
        "fetch_hours": float(args.hours),
        "start_unix": start,
        "end_unix": end,
        "symbols": list(PERP_SYMBOLS),
        "candles": candles,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
