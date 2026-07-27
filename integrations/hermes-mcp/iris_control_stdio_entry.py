"""Hermes stdio MCP entry — absolute script, no PYTHONPATH required.

Hermes StdioServerParameters does not pass config ``cwd``, so ``python -m``
with PYTHONPATH is fragile. This file bootstraps the repo onto sys.path.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_root_s = str(_ROOT)
if _root_s not in sys.path:
    sys.path.insert(0, _root_s)

from iris.mcp.iris_control_stdio import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
