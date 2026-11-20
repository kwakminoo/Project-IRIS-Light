"""CLOSED — platform api_server pin ≠ product chat toolset enable.

Invariant (ToolsetBoundary):
  computer_use ∈ platform_toolsets.api_server pin
  AND computer_use ∈ chat disabled_toolsets
  → model never sees Hermes desktop control on InternalSidecar chat.

``hermes-api-server`` is a platform composite label only; it is not a chat
toolset name and must not be required in sidecar disabled_toolsets.

Source of truth: ``_IRIS_DISABLED_TOOLSETS`` / ``_IRIS_API_SERVER_TOOLSETS``.
Wired into ``_check_agent_merge_policy_closed`` so one command locks CLOSED.
"""

from __future__ import annotations

import ast
from pathlib import Path

from iris.engine._check_sidecar_disables_agent_file_terminal import (
    _disabled_toolsets_literals,
)
from iris.system.iris_agent_control_sync import (
    _IRIS_API_SERVER_TOOLSETS,
    _IRIS_DISABLED_TOOLSETS,
)

_SIDECAR = Path(__file__).resolve().parents[1] / "engine" / "_sidecar_main.py"


def main() -> None:
    product = frozenset(_IRIS_DISABLED_TOOLSETS)
    pin = frozenset(_IRIS_API_SERVER_TOOLSETS)

    assert "hermes-api-server" in pin, pin
    assert "computer_use" in pin, pin
    assert "computer_use" in product, product

    src = _SIDECAR.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(_SIDECAR))
    literals = _disabled_toolsets_literals(tree)
    assert literals, "sidecar must pass disabled_toolsets to AIAgent"
    sidecar_set = frozenset(literals[0])
    assert sidecar_set == product, (
        f"sidecar disabled_toolsets != _IRIS_DISABLED_TOOLSETS: "
        f"extra={sorted(sidecar_set - product)} "
        f"missing={sorted(product - sidecar_set)}"
    )
    # Platform composite label is not a chat toolset name.
    assert "hermes-api-server" not in sidecar_set, (
        "hermes-api-server is api_server pin label, not a chat disabled_toolsets entry"
    )
    assert "hermes-api-server" not in product, (
        "hermes-api-server must not be in product chat disabled set"
    )

    print(
        "toolset_platform_chat_boundary ok",
        f"disabled={sorted(product)}",
        f"api_server_pin={sorted(pin)}",
        "computer_use=pin+disabled",
        "hermes-api-server=pin_only",
    )


if __name__ == "__main__":
    main()
