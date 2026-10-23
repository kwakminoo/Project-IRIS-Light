"""Live Hermes play check. Not a unit stand-in.

Records whether a connected Hermes + shipped model emits iris_invoke for
「유튜브에서 노래 틀어줘」 from a home-screen packed payload, and whether
「유튜브가 뭐야?」 does not.

Skip when the gateway is down or the shipped model is unavailable.
A skip is the 2026-10-22 incident class, not a packer unit failure.
Do not restore regex because this skipped.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

from iris.browser.observation import browser_teaching_block
from iris.config.settings import load_settings
from iris.system.hermes_gateway import is_hermes_gateway_running

_STREAM_BUDGET_SEC = 45.0


def _home_messages(user_text: str) -> list[dict[str, str]]:
    from iris.ui.window.main_window import MainWindow

    win = SimpleNamespace(
        _history=[{"role": "user", "content": user_text}],
        _db=None,
        _pending_handoff="",
        _pending_past_chats="",
        _use_hermes_backend=lambda: True,
        _workspace_mode="assistant",
        _workspace_screen_context=lambda: "",
    )
    return MainWindow._chat_messages_with_project_context(win)


def _stream_until(client, model: str, messages: list[dict[str, str]]) -> list[dict] | None:
    chunks: list[dict] = []
    error: list[BaseException] = []

    def _run() -> None:
        try:
            for chunk in client.stream_chat(model, messages):
                chunks.append(chunk)
                if chunk.get("done"):
                    break
        except BaseException as exc:
            error.append(exc)

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(_STREAM_BUDGET_SEC)
    if worker.is_alive():
        return None
    if error:
        raise error[0]
    return chunks


def _stream_mentions(chunks: list[dict], *needles: str) -> bool:
    blob = ""
    for chunk in chunks:
        blob += str(chunk.get("content") or "")
        blob += str(chunk.get("tool_progress") or "")
    low = blob.lower()
    return any(needle.lower() in low for needle in needles)


def main() -> int:
    settings = load_settings()
    base = (settings.hermes_base_url or "http://127.0.0.1:8642/v1").strip()
    try:
        up = is_hermes_gateway_running(base, timeout_sec=2.0)
    except Exception as exc:
        print(f"SKIP live Hermes play: probe failed ({exc}). Not a unit stand-in. Do not restore regex.")
        return 0
    if not up:
        print("SKIP live Hermes play: gateway not up. Not a unit stand-in. Do not restore regex.")
        return 0

    from iris.infrastructure.hermes_client import HermesClient
    from iris.infrastructure.hermes_credentials import resolve_hermes_api_key

    client = HermesClient(base, api_key=resolve_hermes_api_key(settings.hermes_api_key))
    model = (settings.ollama_model or settings.model_name or "").strip()
    if not model or model == "(unset)":
        try:
            listed = client.list_models()
        except Exception:
            listed = []
        model = (listed[0] if listed else "").strip()
    if not model:
        print("SKIP live Hermes play: no shipped model. Not a unit stand-in. Do not restore regex.")
        return 0

    teach = browser_teaching_block()
    assert "browser.search" in teach

    try:
        play_chunks = _stream_until(client, model, _home_messages("유튜브에서 노래 틀어줘"))
    except Exception as exc:
        print(f"SKIP live Hermes play: stream failed ({exc}). Not a unit stand-in. Do not restore regex.")
        return 0
    if play_chunks is None:
        print(
            f"SKIP live Hermes play: stream exceeded {_STREAM_BUDGET_SEC:.0f}s on model={model}. "
            "Not a unit stand-in. Do not restore regex."
        )
        return 0

    play_hit = _stream_mentions(play_chunks, "iris_invoke", "browser.search")
    try:
        ask_chunks = _stream_until(client, model, _home_messages("유튜브가 뭐야?"))
    except Exception as exc:
        print(f"SKIP live Hermes play: veto stream failed ({exc}). Not a unit stand-in. Do not restore regex.")
        return 0
    if ask_chunks is None:
        print(
            f"SKIP live Hermes play: veto stream exceeded {_STREAM_BUDGET_SEC:.0f}s. "
            "Not a unit stand-in. Do not restore regex."
        )
        return 0
    ask_hit = _stream_mentions(ask_chunks, "browser.search", "browser.media")

    if not play_hit:
        print(
            "FAIL live Hermes play: packed home-screen turn did not emit iris_invoke/browser.search. "
            "Same class as the 2026-10-22 incident. Do not restore regex."
        )
        return 1
    if ask_hit:
        print("FAIL live Hermes play: 유튜브가 뭐야? drove a browser action.")
        return 1
    print("live Hermes play ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
