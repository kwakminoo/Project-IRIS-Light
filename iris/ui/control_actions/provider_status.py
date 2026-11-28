"""Provider boundary probes for image_generate / text_to_speech absorbs.

L2 contract: status / availability only — never invent image bytes or audio.
Real Desktop Voice TTS enqueue stays behind human confirm (not auto-wired here).
"""

from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry, ok_result


def register_provider_status_actions(window: Any, registry: ActionRegistry) -> None:
    def image_status(_args: dict[str, Any]) -> dict[str, Any]:
        # No Native image provider Speak path yet — honest unsupported.
        return ok_result(
            "image.status",
            {
                "provider": None,
                "status": "not_installed",
                "supported": False,
                "payload": None,
                "note": (
                    "Iris has no Speak image-generation provider. "
                    "Do not invent image bytes. Use vision.analyze_attachment for "
                    "understanding attached images."
                ),
            },
        )

    def voice_tts_status(_args: dict[str, Any]) -> dict[str, Any]:
        prefs = getattr(window, "_voice_prefs", None)
        runtime_ready = bool(getattr(window, "_tts_runtime_ready", False))
        tts_enabled = bool(getattr(prefs, "tts_enabled", False)) if prefs is not None else False
        if not tts_enabled:
            status = "needs_approval"
            note = (
                "Desktop Voice TTS exists but is not enabled for model enqueue. "
                "Ask the user to enable TTS in settings; do not invent audio bytes."
            )
        elif not runtime_ready:
            status = "not_installed"
            note = (
                "TTS runtime is not ready. Bootstrap/runtime install required. "
                "Do not invent audio bytes."
            )
        else:
            # Ready locally, but model-driven enqueue is still confirm-gated (L2).
            status = "needs_approval"
            note = (
                "TTS runtime is ready for Desktop Voice. Model-driven speak "
                "requires user confirmation; this tool returns status only."
            )
        return ok_result(
            "voice.tts_status",
            {
                "provider": "desktop_voice",
                "status": status,
                "supported": True,
                "runtime_ready": runtime_ready,
                "tts_enabled": tts_enabled,
                "payload": None,
                "note": note,
            },
        )

    registry.register(
        "image.status",
        image_status,
        summary=(
            "Probe image-generation provider availability. Returns not_installed "
            "when no provider is wired. Never returns image bytes. "
            "Hermes image_generate absorb (L2 status-only)."
        ),
        risk="low",
        confirm_required=False,
    )
    registry.register(
        "voice.tts_status",
        voice_tts_status,
        summary=(
            "Probe Desktop Voice TTS availability (not_installed|needs_approval). "
            "Never returns audio bytes. Hermes text_to_speech absorb (L2 status-only)."
        ),
        risk="low",
        confirm_required=False,
    )
