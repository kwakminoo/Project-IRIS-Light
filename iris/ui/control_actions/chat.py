"""채팅 세션·마이크·활동 로그 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import ChatHost

def register_chat_actions(window: ChatHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        _log,
        err_result,
        ok_result,
    )

    def chat_set_model(args: dict[str, Any]) -> dict[str, Any]:
        model = str(args.get("model") or "").strip()
        if not model:
            return err_result("chat.set_model", "model required")
        window._apply_selected_model(model, persist=True)
        combo = getattr(window._chat, "_model_combo", None)
        if combo is not None:
            for i in range(combo.count()):
                if combo.itemData(i) == model or combo.itemText(i) == model:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(i)
                    combo.blockSignals(False)
                    break
        _log(window, "chat.set_model", True)
        return ok_result("chat.set_model", {"model": model})

    def chat_clear_history(_a: dict[str, Any]) -> dict[str, Any]:
        window.reset_current_conversation()
        _log(window, "chat.clear_history", True)
        return ok_result(
            "chat.clear_history",
            {"history_len": 0, "conversation_id": window._conversation_id},
        )

    def chat_new_session(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_new_chat_requested()
        _log(window, "chat.new_session", True)
        return ok_result(
            "chat.new_session",
            {"conversation_id": window._conversation_id},
        )

    def chat_list_sessions(args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.conversations import list_conversations

        try:
            limit = int(args.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20
        items = list_conversations(
            window._db,
            limit=max(1, min(limit, 100)),
            include_empty_id=window._conversation_id,
        )
        return ok_result(
            "chat.list_sessions",
            {
                "active_id": window._conversation_id,
                "sessions": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "message_count": c.message_count,
                        "updated_at": c.updated_at,
                    }
                    for c in items
                ],
            },
        )

    def chat_open_session(args: dict[str, Any]) -> dict[str, Any]:
        from iris.storage.conversations import get_conversation

        raw = args.get("id") if args.get("id") is not None else args.get("conversation_id")
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            return err_result("chat.open_session", "id required")
        if get_conversation(window._db, cid) is None:
            return err_result("chat.open_session", f"conversation {cid} not found")
        window._on_conversation_selected(cid)
        _log(window, "chat.open_session", True)
        return ok_result("chat.open_session", {"conversation_id": cid})

    def chat_stop(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_chat_stop()
        _log(window, "chat.stop", True)
        return ok_result("chat.stop", {})

    def voice_toggle_mic(_a: dict[str, Any]) -> dict[str, Any]:
        window._on_chat_mic_clicked()
        mic = getattr(window, "_mic", None)
        state = getattr(getattr(mic, "state", None), "value", str(getattr(mic, "state", "")))
        _log(window, "voice.toggle_mic", True)
        return ok_result("voice.toggle_mic", {"mic_state": state})

    def voice_mic_off(_a: dict[str, Any]) -> dict[str, Any]:
        window._set_mic_listen(False)
        mic = getattr(window, "_mic", None)
        state = getattr(getattr(mic, "state", None), "value", str(getattr(mic, "state", "")))
        _log(window, "voice.mic_off", True)
        return ok_result("voice.mic_off", {"mic_state": state, "listening": False})

    def voice_mic_on(_a: dict[str, Any]) -> dict[str, Any]:
        window._set_mic_listen(True)
        mic = getattr(window, "_mic", None)
        state = getattr(getattr(mic, "state", None), "value", str(getattr(mic, "state", "")))
        _log(window, "voice.mic_on", True)
        return ok_result("voice.mic_on", {"mic_state": state})

    def voice_mic_status(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.audio.microphone_controller import MicState

        mic = getattr(window, "_mic", None)
        state = getattr(getattr(mic, "state", None), "value", str(getattr(mic, "state", "")))
        listening = bool(
            mic is not None and getattr(mic, "state", None) not in (MicState.OFF, MicState.ERROR)
        )
        return ok_result(
            "voice.mic_status",
            {
                "mic_state": state,
                "listening": listening,
                "stt_enabled": bool(getattr(window._voice_prefs, "stt_enabled", False)),
                "preferred": bool(
                    getattr(window._voice_prefs, "mic_listen_preferred", False)
                ),
            },
        )

    def activity_log(args: dict[str, Any]) -> dict[str, Any]:
        text = str(args.get("text") or args.get("message") or "").strip()
        if not text:
            return err_result("activity.log", "text required")
        window._live_activity.append_instant_line(text)
        return ok_result("activity.log", {})

    def notify_add(args: dict[str, Any]) -> dict[str, Any]:
        title = str(args.get("title") or "Iris").strip()
        message = str(args.get("message") or args.get("text") or "").strip()
        category = str(args.get("category") or "INFO").strip() or "INFO"
        window._notes.try_add_alert(
            target_id=0,
            category=category,
            title=title,
            message=message,
            focus_hint="",
            event_id=0,
        )
        return ok_result("notify.add_alert", {"title": title})

    reg.register(
        "chat.set_model",
        chat_set_model,
        summary="Select chat/Ollama model and sync Hermes",
        risk="medium",
    )

    reg.register(
        "chat.clear_history",
        chat_clear_history,
        summary="Clear the current chat session (context, transcript and stored messages)",
        risk="medium",
        confirm_required=True,
    )

    reg.register(
        "chat.new_session",
        chat_new_session,
        summary="Start a new chat session (same as sidebar CHATS +)",
        risk="low",
    )

    reg.register(
        "chat.list_sessions",
        chat_list_sessions,
        summary="List saved chat sessions (id, title, message_count)",
        risk="low",
    )

    reg.register(
        "chat.open_session",
        chat_open_session,
        summary="Switch to a saved chat session by id (args.id)",
        risk="low",
    )

    reg.register(
        "chat.stop",
        chat_stop,
        summary="Stop current chat turn (same as Stop button)",
        risk="low",
    )

    reg.register(
        "voice.toggle_mic",
        voice_toggle_mic,
        summary="Toggle mic listen (same as titlebar mic icon)",
        risk="medium",
    )

    reg.register(
        "voice.mic_off",
        voice_mic_off,
        summary="Turn microphone listen off",
        risk="low",
    )

    reg.register(
        "voice.mic_on",
        voice_mic_on,
        summary="Turn microphone listen on (requires STT enabled)",
        risk="medium",
    )

    reg.register(
        "voice.mic_status",
        voice_mic_status,
        summary="Get mic listen / STT status",
        risk="low",
    )

    reg.register("activity.log", activity_log, summary="Append Live Activity line")

    reg.register("notify.add_alert", notify_add, summary="Add notification alert row")
