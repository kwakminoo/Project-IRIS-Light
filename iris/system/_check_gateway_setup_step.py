"""Deprecated alias — product setup uses engine ensure_ready, not :8642 gateway.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_engine_setup_step
"""

from __future__ import annotations

from iris.system._check_iris_agent_engine_setup_step import _main


if __name__ == "__main__":
    _main()
