"""Product agent_runtime setup step — sidecar probe, no :8642 start.

Unit 0 Delete: product setup must not boot HTTP gateway. Lifecycle abort
coverage that needed a live :8642 is obsolete here; see gateway module
checks / Unit 2 gut for remaining start/restart helpers.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_gateway_setup_step
"""

from __future__ import annotations

import ast
import time
from pathlib import Path
from unittest.mock import patch

from iris.system.setup_protocol import SetupProtocol

_ROOT = Path(__file__).resolve().parents[2]
_SETUP = _ROOT / "iris" / "system" / "setup_protocol.py"
_FORBIDDEN_IN_STEP = frozenset(
    {
        "ensure_iris_agent_gateway_running",
        "restart_iris_agent_gateway",
        "start_iris_agent_gateway",
    }
)


def _check_step_source_no_gateway_ops() -> None:
    tree = ast.parse(_SETUP.read_text(encoding="utf-8-sig"), filename=str(_SETUP))
    target: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_step_agent_runtime":
                target = node
                break
    assert target is not None, "_step_agent_runtime missing"
    hits: list[str] = []
    for node in ast.walk(target):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_IN_STEP:
            hits.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_IN_STEP:
            hits.append(node.attr)
    assert not hits, f"_step_agent_runtime must not call gateway ops: {hits}"


def _check_product_step_sidecar_wording() -> None:
    streams: list[str] = []
    proto = SetupProtocol(dry_run=True, simulate=True)
    proto.bind_stream(lambda t, _p, _r: streams.append(t or ""))

    # Avoid live install / MCP / ensure side effects; assert contract + wording.
    with (
        patch.object(
            proto,
            "_install_agent",
            side_effect=AssertionError("product step must not auto-install here"),
        ),
        patch(
            "iris.system.setup_protocol.probe_agent_runtime",
            return_value=(True, "venv ok (python.exe)"),
        ),
        patch(
            "iris.system.setup_protocol.ensure_iris_agent_runtime",
        ) as ensure_rt,
        patch(
            "iris.system.setup_protocol.verify_iris_mcp_tools",
            return_value=(True, "SpeakTools ok"),
        ),
        patch(
            "iris.system.setup_protocol.resolve_agent_api_key",
            return_value="test-key",
        ),
    ):
        class _Ok:
            ok = True
            messages: list[str] = []

        ensure_rt.return_value = _Ok()
        t0 = time.monotonic()
        result = proto._step_agent_runtime()
        dt = time.monotonic() - t0

    assert result.status == "done", result
    assert "sidecar" in (result.message or "").lower(), result.message
    assert "8642" not in (result.message or ""), result.message
    assert "gateway listening" not in (result.message or "").lower()
    blob = "\n".join(streams).lower()
    assert "sidecar" in blob or "speaktools" in blob, streams
    assert "listening :8642" not in blob and "gateway listening" not in blob
    kwargs = ensure_rt.call_args.kwargs
    assert kwargs.get("start_gateway") is False
    assert dt < 10.0, dt


def _main() -> None:
    _check_step_source_no_gateway_ops()
    _check_product_step_sidecar_wording()
    print("gateway_step check ok (product sidecar; no :8642 boot)")


if __name__ == "__main__":
    _main()
