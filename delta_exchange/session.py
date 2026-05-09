from __future__ import annotations

import os

import requests

from delta_exchange.constants import rest_base_url


def build_rest_session() -> requests.Session:
    """Session for Delta REST. Optional ``DELTA_API_KEY`` → ``api-key`` header."""
    s = requests.Session()
    s.headers["Accept"] = "application/json"
    key = (os.environ.get("DELTA_API_KEY") or "").strip()
    if key:
        s.headers["api-key"] = key
    return s


def rest_get(path: str, *, params: dict | None = None, session: requests.Session | None = None):
    """GET ``path`` (e.g. ``/v2/history/candles``) against configured REST base."""
    base = rest_base_url().rstrip("/")
    sess = session or build_rest_session()
    return sess.get(f"{base}{path}", params=params or {}, timeout=60)
