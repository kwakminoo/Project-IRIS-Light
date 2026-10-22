"""Self-check: high-confidence browser intents, not chat."""

from __future__ import annotations

from iris.browser.intent import format_browser_reply, match_browser_intent


def main() -> int:
    play = match_browser_intent("유튜브에서 노래 하나 아무거나 틀어줘")
    assert play is not None and play.kind == "play"
    assert play.control == "browser.search"
    assert play.args["engine"] == "youtube" and play.args["play"] is True
    assert play.args["query"] == "음악"

    named = match_browser_intent("아이유 밤편지 틀어줘")
    assert named is not None and named.args["query"] == "아이유 밤편지"

    pause = match_browser_intent("영상 일시정지 해줘")
    assert pause is not None and pause.kind == "pause"

    resume = match_browser_intent("다시 재생해줘")
    assert resume is not None and resume.kind == "resume"

    search = match_browser_intent("유튜브에서 아이유 검색해줘")
    assert search is not None and search.kind == "search" and search.args.get("play") is None

    for chat in (
        "유튜브가 뭐야",
        "음악을 좋아해",
        "오늘 날씨 어때",
        "코드 리뷰해줘",
    ):
        assert match_browser_intent(chat) is None, chat

    reply = format_browser_reply(
        play,
        {
            "ok": True,
            "result": {
                "title": "lofi",
                "browser_playing": True,
                "media": {"playing": True, "ad": False},
            },
        },
    )
    assert "재생을 시작" in reply
    assert "스피커" in reply
    fail = format_browser_reply(play, {"ok": False, "result": {"browser_media_block": "consent"}})
    assert "동의" in fail

    from pathlib import Path

    body = Path(__file__).resolve().parents[1] / "ui" / "window" / "main_window.py"
    src = body.read_text(encoding="utf-8")
    hook = src.index("if self._try_local_browser_control(turn):")
    gate = src.index("owns = hermes_owns_local_intents(self._use_hermes_backend())")
    assert hook < gate, "browser router must run before Hermes-owned-intent skip"

    print("browser intent ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
