#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
  exec ".venv/bin/python" -m iris
fi

exec python3 -m iris
