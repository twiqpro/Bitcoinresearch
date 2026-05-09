from __future__ import annotations

import os

# Per user scope: perpetual futures quoted against USD — India production host.
PERP_SYMBOLS = ("BTCUSD", "ETHUSD")


def rest_base_url() -> str:
    return os.environ.get("DELTA_REST_BASE", "https://api.india.delta.exchange")


def ws_public_url() -> str:
    return os.environ.get("DELTA_WS_URL", "wss://public-socket.india.delta.exchange")
