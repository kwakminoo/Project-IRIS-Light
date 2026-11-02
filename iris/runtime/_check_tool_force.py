"""ToolForcePolicy 자검 — required 플래그·respond unwrap·사이드이펙트 정직.

  .venv\\Scripts\\python.exe -m iris.runtime._check_tool_force
"""

from __future__ import annotations

from types import SimpleNamespace

from iris.runtime.tool_force import (
    EXIT_TOOL_NAMES,
    honesty_rejects_side_effect_success,
    side_effect_goal,
    unwrap_respond_payload,
)
from iris.runtime.turn_followthrough import counts_as_tool_ok
from iris.runtime.turn_verify import SIDE_EFFECT_EXPLICIT_FAIL, TurnEvidence, verify_file_create_turn
from iris.system.hermes_tool_choice import iris_tool_force_policy
from iris.ui.chat.file_write_claim import CHAT_ONLY


def main() -> None:
    policy = iris_tool_force_policy()
    assert policy["first_llm_step"] == "required", policy
    assert policy["exit_tool"] == "respond", policy
    assert "respond" in EXIT_TOOL_NAMES

    # Vendor overlay module (Hermes PR #145164 shape)
    import importlib.util
    from pathlib import Path

    overlay = (
        Path(__file__).resolve().parents[2]
        / "vendor"
        / "iris-agent-runtime"
        / "overlays"
        / "tool_choice"
        / "tool_choice.py"
    )
    spec = importlib.util.spec_from_file_location("iris_overlay_tool_choice", overlay)
    assert spec and spec.loader
    tc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tc)
    assert tc.RESPOND_TOOL_NAME == "respond"
    agent = SimpleNamespace(
        _tool_choice="required",
        api_mode="chat_completions",
        platform="cli",
        base_url="http://127.0.0.1:11434/v1",
        provider="custom",
        _tool_choice_disabled=False,
    )
    tools = [{"type": "function", "function": {"name": "project_run", "parameters": {}}}]
    out_tools, overrides = tc.apply_tool_choice(agent, tools, {})
    assert overrides.get("tool_choice") == "required", overrides
    names = [(t.get("function") or {}).get("name") for t in out_tools]
    assert "respond" in names, names
    assert "project_run" in names

    # auto / no tools / override wins
    agent_auto = SimpleNamespace(
        _tool_choice="auto",
        api_mode="chat_completions",
        platform="cli",
        _tool_choice_disabled=False,
    )
    t2, o2 = tc.apply_tool_choice(agent_auto, tools, {})
    assert "tool_choice" not in o2
    assert t2 is tools
    t3, o3 = tc.apply_tool_choice(agent, tools, {"tool_choice": "auto"})
    assert o3["tool_choice"] == "auto"

    # respond unwrap → plain text
    msg = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(name="respond", arguments='{"message":"열린 프로젝트는 demo 입니다"}')
        ],
        content="",
        finish_reason="tool_calls",
    )
    assert tc.unwrap_respond_call(msg) is True
    assert msg.content == "열린 프로젝트는 demo 입니다"
    assert msg.tool_calls is None
    assert msg.finish_reason == "stop"

    iris_u = unwrap_respond_payload("respond", '{"message":"hi"}')
    assert iris_u.was_respond and iris_u.plain_text == "hi"

    assert side_effect_goal("달력 실행해줘")
    assert side_effect_goal("달력 스크립트 만들어줘")
    assert not side_effect_goal("지금 열린 프로젝트가 뭔지 알려줘")

    assert not counts_as_tool_ok("respond ok")
    assert counts_as_tool_ok("project.run ok")

    # 실행 goal + tool_ok==0 + respond only → 성공 표시 아님
    # (파일확장자·「스크립트」 없는 실행 문구 — file_create_goal 과 갈라짐)
    run_goal = "달력 실행해줘"
    assert honesty_rejects_side_effect_success(
        goal=run_goal,
        tool_ok_count=0,
        exit_tool_seen=True,
    )
    run_fail = verify_file_create_turn(
        TurnEvidence(
            tool_ok_count=0,
            tool_written=False,
            verified_path="",
            content_match=None,
            empty_reply=False,
            assistant="실행했습니다",
            goal=run_goal,
            exit_tool_seen=True,
        )
    )
    assert "stop" in run_fail.actions
    assert SIDE_EFFECT_EXPLICIT_FAIL in run_fail.display

    # demotion helpers present (temp file — do not touch live Hermes demotion list)
    import tempfile
    from pathlib import Path as _P

    assert tc.looks_like_tool_choice_rejection(
        "Error code: 400 - 'tool_choice' must be one of none, auto"
    )
    with tempfile.TemporaryDirectory(prefix="iris-tool-choice-") as tmp:
        demote_file = _P(tmp) / "tool_choice_demoted.json"
        tc._demotion_path = lambda: demote_file  # type: ignore[method-assign]
        line = tc.demote_tool_choice_for_endpoint(agent, reason="unit-test")
        assert "auto" in line
        assert tc.tool_choice_required(agent) is False
        assert demote_file.is_file()

    print("tool_force ok", policy["exit_tool"], CHAT_ONLY[:4])


if __name__ == "__main__":
    main()
