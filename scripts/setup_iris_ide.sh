#!/usr/bin/env bash
# IRIS IDE (Theia) optional runtime — thin wrapper; orchestration lives in Python.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python required." >&2
  exit 1
fi
exec "$PY" - <<'PY'
from iris.system.iris_ide_runtime import IrisIdeRuntimeManager

mgr = IrisIdeRuntimeManager()
ok, msg = mgr.install(progress=lambda m: print(m, flush=True))
print("install:", ok, msg)
raise SystemExit(0 if ok else 1)
PY
