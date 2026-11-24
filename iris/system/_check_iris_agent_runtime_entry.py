"""Iris-owned sidecar entrypoint contract."""

from __future__ import annotations

import inspect
from pathlib import Path


def main() -> None:
    from iris.engine import _sidecar_main
    source = inspect.getsource(_sidecar_main._import_agent_class)
    assert '_load_local_helper("agent_entry")' in source
    assert '"run_agent"' not in source

    entry = Path(_sidecar_main.__file__).with_name("agent_entry.py")
    text = entry.read_text(encoding="utf-8")
    assert "from run_agent import AIAgent" in text
    compile(text, str(entry), "exec")

    print("iris_agent_runtime_entry ok")


if __name__ == "__main__":
    main()
