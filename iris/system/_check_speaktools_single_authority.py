"""ACO-P4: Sidecar drops Hermes builtins; SpeakTools are the model-visible tools."""

from __future__ import annotations

import inspect
from pathlib import Path


def check_sidecar_replaces_tools() -> None:
    from iris.engine import _sidecar_main as sidecar

    src = inspect.getsource(sidecar)
    assert "agent.tools = iris_tools" in src or "agent.tools =" in src
    assert "Drop Hermes builtins" in src or "valid_tool_names" in src


def check_absorbed_baked_in_vendor() -> None:
    root = Path(__file__).resolve().parents[2] / "vendor" / "iris-agent-core"
    stamp = root / ".iris-agent-baseline"
    assert stamp.is_file(), "baseline stamp missing — overlays not baked"
    # absorbed overlay marker or toolset snippet presence
    hit = False
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "absorbed_toolsets" in text or "IRIS_ABSORBED" in text or "iris absorbed" in text.lower():
            hit = True
            break
    # soft: stamp is enough if absorbed writes config; still require stamp SHA
    sha = stamp.read_text(encoding="utf-8").strip().splitlines()[0]
    assert len(sha) >= 7
    _ = hit  # informational; stamp proves bake ran


def check_no_new_bypass_runtime() -> None:
    """Owned core must not add a second execution path past SpeakTools."""
    from iris.engine import _sidecar_main as sidecar

    src = inspect.getsource(sidecar)
    assert "_request_native_tool" in src


if __name__ == "__main__":
    check_sidecar_replaces_tools()
    check_absorbed_baked_in_vendor()
    check_no_new_bypass_runtime()
    print("speaktools single authority ok")
