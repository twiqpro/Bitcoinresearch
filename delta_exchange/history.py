from __future__ import annotations

import time
from typing import Any

import requests

from delta_exchange.constants import PERP_SYMBOLS, rest_base_url
from delta_exchange.session import build_rest_session

MAX_CANDLES_PER_REQUEST = 2000


def _assert_symbol(symbol: str) -> None:
    if symbol not in PERP_SYMBOLS:
        raise ValueError(f"symbol must be one of {PERP_SYMBOLS}, got {symbol!r}")


def fetch_candles_asc(
    symbol: str,
    resolution: str,
    start: int,
    end: int,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetch OHLC candles for ``start``..``end`` (unix seconds), oldest first."""
    _assert_symbol(symbol)
    sess = session or build_rest_session()
    base = rest_base_url().rstrip("/")
    by_time: dict[int, dict[str, Any]] = {}
    chunk_end = end

    while chunk_end >= start:
        r = sess.get(
            f"{base}/v2/history/candles",
            params={
                "resolution": resolution,
                "symbol": symbol,
                "start": start,
                "end": chunk_end,
            },
            headers={"Accept": "application/json"},
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            raise RuntimeError(f"candles failed: {body}")
        chunk = body.get("result") or []
        if not chunk:
            break
        for row in chunk:
            by_time[row["time"]] = row
        earliest = min(row["time"] for row in chunk)
        if len(chunk) < MAX_CANDLES_PER_REQUEST:
            break
        chunk_end = earliest - 1
        time.sleep(0.15)

    ordered = sorted(by_time.keys())
    return [by_time[t] for t in ordered if start <= t <= end]
