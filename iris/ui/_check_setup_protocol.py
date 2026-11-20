"""시작 프로토콜 모듈 자검 — UI 없이 상태/상수만."""

from __future__ import annotations

from iris.system.setup_protocol import (
    CORE_STEP_IDS,
    OPTIONAL_IDS,
    VISIBLE_CONSOLE_STEPS,
    SetupProtocol,
    SetupStepResult,
    core_needs_user_next,
    default_min_model,
    format_inference_report,
    has_usable_inference_backend,
    iris_state_dir,
    load_setup_state,
    local_inference_models,
    parse_install_percent,
    setup_state_path,
)


def main() -> None:
    assert len(CORE_STEP_IDS) == 10
    assert "voice_full" in OPTIONAL_IDS
    assert "iris_ide" in OPTIONAL_IDS
    assert "learning" in OPTIONAL_IDS
    assert default_min_model()
    r = SetupStepResult("state_init", "pending")
    assert r.label
    st = load_setup_state()
    assert "core_ready" in st
    assert "voice_full" in st.get("optional", {})
    assert "learning" in st.get("optional", {})
    proto = SetupProtocol()
    snap = proto.detect()
    assert "ollama_exe" in snap
    assert "agent_exe" in snap
    assert "hermes_exe" not in snap
    assert "local_model_count" in snap
    assert local_inference_models(["llama3.2:latest", "gemma4:31b-cloud"]) == ["llama3.2:latest"]
    assert not has_usable_inference_backend(["minimax-m3:cloud"], cloud_signed_in=False)
    rec = format_inference_report(
        local_models=[], cloud_signed_in=True, min_model="gemma4:e2b"
    )
    assert "권장" in rec
    card = SetupStepResult(
        "ollama_cloud",
        "needs_user",
        can_install=True,
        can_login=True,
        install_label="최소 모델 설치",
    )
    assert card.can_login and card.install_label == "최소 모델 설치"
    assert card.login_label == "로그인"
    d = iris_state_dir()
    assert d.is_dir()
    assert parse_install_percent("  ████  42%") == 42
    assert parse_install_percent("pulling manifest") is None
    from iris.ui.window.setup_wizard import _STREAM_STEPS

    assert "agent_runtime" in _STREAM_STEPS and "core_smoke" in _STREAM_STEPS
    assert "agent_install" in CORE_STEP_IDS
    assert "agent_env" in CORE_STEP_IDS
    assert "agent_provider" in CORE_STEP_IDS
    for legacy in ("hermes_install", "hermes_env", "hermes_provider"):
        assert legacy not in CORE_STEP_IDS
        assert legacy not in _STREAM_STEPS
    assert VISIBLE_CONSOLE_STEPS == frozenset(
        {"ollama_install", "agent_install", "emulator"}
    )
    assert {"agent_install", "agent_env", "agent_provider"} <= _STREAM_STEPS
    from iris.system.setup_protocol import normalize_setup_step_id

    assert normalize_setup_step_id("hermes_install") == "agent_install"
    assert normalize_setup_step_id("agent_env") == "agent_env"
    assert core_needs_user_next("skip", allow_skip=False) == "reverify"
    assert core_needs_user_next("skip", allow_skip=True) == "skip"
    assert "last_verify" in st
    print("setup_protocol check ok", setup_state_path(), "detect.keys=", sorted(snap))


if __name__ == "__main__":
    main()
