#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[dev]'
(cd frontend && npm ci)
atlas demo --cached
echo 'Ready. Run: .venv/bin/python scripts/dev.py'
