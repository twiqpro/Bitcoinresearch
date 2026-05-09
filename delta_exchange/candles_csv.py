from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


COLUMNS = ("time", "open", "high", "low", "close", "volume")


def write_candles_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in COLUMNS})


def read_candles_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def candle_rows_from_file(path: Path) -> list[dict[str, Any]]:
    """Load CSV written by ``write_candles_csv`` (coerce numeric types)."""
    raw = read_candles_csv(path)
    out = []
    for r in raw:
        out.append(
            {
                "time": int(float(r["time"])),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
            }
        )
    return out


def write_fetch_meta(
    path: Path,
    *,
    resolution: str,
    start: int,
    end: int,
    symbols: tuple[str, ...],
    files: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "resolution": resolution,
        "start_unix": start,
        "end_unix": end,
        "symbols": list(symbols),
        "csv_files": files,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
