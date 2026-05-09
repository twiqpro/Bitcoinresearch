#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
./.venv/bin/python export_dashboard_data.py
./.venv/bin/python export_delta_dashboard.py --hours 168 --resolution 5m
cd btc-dashboard
npm run build
echo ""
echo "Dashboard data + dist updated."
echo "Preview:  cd btc-dashboard && npm run preview -- --host 127.0.0.1 --port 4173"
echo "Then open http://127.0.0.1:4173/"
