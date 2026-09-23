#!/usr/bin/env bash
set -euo pipefail
python3 tools/fetch_snapshot.py --destination "${1:-data/raw/snapshot}"
