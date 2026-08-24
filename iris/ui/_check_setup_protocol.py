"""시작 프로토콜 모듈 자검 — UI 없이 상태/상수만."""

from __future__ import annotations

from iris.system.setup_protocol import (
    CORE_STEP_IDS,
    OPTIONAL_IDS,
    SetupProtocol,
    SetupStepResult,
    default_min_model,
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
    assert "local_model_count" in snap
    assert local_inference_models(["llama3.2:latest", "gemma4:31b-cloud"]) == ["llama3.2:latest"]
    assert not has_usable_inference_backend(["minimax-m3:cloud"], cloud_signed_in=False)
    d = iris_state_dir()
    assert d.is_dir()
    assert parse_install_percent("  ████  42%") == 42
    assert parse_install_percent("pulling manifest") is None
    print("setup_protocol check ok", setup_state_path(), "detect.keys=", sorted(snap))


if __name__ == "__main__":
    main()
