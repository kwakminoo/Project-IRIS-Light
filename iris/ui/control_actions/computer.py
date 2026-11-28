"""Native computer.surfaces — honest product surface map (Hermes computer_use).

Observe-only. No raw desktop click API. Act routes to existing Speak tools.
"""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, ok_result

# Product surfaces Iris actually owns. raw_desktop is explicitly unsupported.
_SUPPORTED = (
    {
        "id": "browser",
        "speak_tools": (
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_snapshot",
        ),
        "note": "Use browser_* Speak tools for web UI",
    },
    {
        "id": "ide",
        "speak_tools": (
            "ide_open_folder",
            "ide_edit",
            "terminal",
            "write_file",
            "read_file",
        ),
        "note": "Use IDE / project / terminal Speak tools — not desktop clicks",
    },
    {
        "id": "emulator",
        "speak_tools": (
            "emulator_status",
            "emulator_tap",
            "emulator_screenshot",
        ),
        "note": "Android emulator surface only",
    },
    {
        "id": "learning",
        "speak_tools": ("learning_list", "learning_status", "skill_view"),
        "note": "Learned skills / showui paths — not raw OS desktop",
    },
)

_UNSUPPORTED = ("raw_desktop",)


def register_computer_actions(registry: ActionRegistry) -> None:
    def computer_surfaces(_args: dict[str, Any]) -> dict[str, Any]:
        return ok_result(
            "computer.surfaces",
            {
                "supported": list(_SUPPORTED),
                "unsupported": list(_UNSUPPORTED),
                "act": (
                    "Call the listed Speak tools for the target surface. "
                    "Iris does not expose a generic desktop click/type API."
                ),
                "observe_only": True,
            },
        )

    registry.register(
        "computer.surfaces",
        computer_surfaces,
        summary=(
            "List Iris-supported computer surfaces (browser/IDE/emulator/learning) "
            "and explicitly mark raw_desktop unsupported. Hermes computer_use absorb."
        ),
        risk="low",
        confirm_required=False,
    )
