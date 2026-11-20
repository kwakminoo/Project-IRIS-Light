"""Self-check for local_model_catalog (registry + join helpers)."""

from __future__ import annotations

from iris.infrastructure.local_model_catalog import (
    OLLAMA_LIBRARY_URL,
    RECOMMENDED_LOCAL_MODELS,
    brand_id_from_pull_name,
    group_by_brand,
    is_installed,
    parse_ollama_cli,
    with_install_flags,
)
from iris.infrastructure.local_vision import DEFAULT_VISION_MODEL
from iris.system.setup_protocol import DEFAULT_MIN_MODEL


def main() -> None:
    assert RECOMMENDED_LOCAL_MODELS, "recommended catalog empty"
    pulls = {e.pull_name for e in RECOMMENDED_LOCAL_MODELS}
    assert DEFAULT_MIN_MODEL in pulls
    assert DEFAULT_VISION_MODEL in pulls
    assert "gemma4:e2b" in pulls
    assert "qwen2.5vl:3b" in pulls
    assert any(e.pull_name == "bge-m3" and e.modality == "embedding" for e in RECOMMENDED_LOCAL_MODELS)
    assert any(
        e.modality == "chat" and e.pull_name != "gemma4:e2b"
        for e in RECOMMENDED_LOCAL_MODELS
    )
    assert OLLAMA_LIBRARY_URL == "https://ollama.com/library"

    assert brand_id_from_pull_name("gemma4:e2b") == "gemma"
    assert brand_id_from_pull_name("qwen2.5vl:3b") == "qwen"
    assert brand_id_from_pull_name("llama3.2:3b") == "llama"
    assert brand_id_from_pull_name("bge-m3") == "bge"

    grouped = group_by_brand(RECOMMENDED_LOCAL_MODELS)
    assert grouped
    brand_order = [bid for bid, _ in grouped]
    # first-seen order from the registry tuple
    expected_brands: list[str] = []
    for e in RECOMMENDED_LOCAL_MODELS:
        if e.brand_id not in expected_brands:
            expected_brands.append(e.brand_id)
    assert brand_order == expected_brands
    flat = [e for _, bucket in grouped for e in bucket]
    assert flat == list(RECOMMENDED_LOCAL_MODELS)

    assert is_installed("gemma4:e2b", {"gemma4:e2b", "llama3.2:3b"}) is True
    assert is_installed("gemma4:e2b", {"gemma4:latest"}) is False
    assert is_installed("bge-m3", {"bge-m3:latest"}) is True
    assert is_installed("bge-m3:latest", {"bge-m3"}) is True
    assert is_installed("llama3.2:3b", set()) is False
    assert is_installed("missing:tag", ["gemma4:e2b"]) is False

    flagged = with_install_flags(
        RECOMMENDED_LOCAL_MODELS,
        {"gemma4:e2b", "bge-m3:latest"},
    )
    by_name = {e.pull_name: flag for e, flag in flagged}
    assert by_name["gemma4:e2b"] is True
    assert by_name["bge-m3"] is True
    assert by_name["qwen2.5vl:3b"] is False
    assert len(flagged) == len(RECOMMENDED_LOCAL_MODELS)

    assert parse_ollama_cli("ollama run qwen3.8") == "qwen3.8"
    assert parse_ollama_cli("ollama pull gemma4:e2b") == "gemma4:e2b"
    assert parse_ollama_cli("$ ollama pull llama3.2:3b") == "llama3.2:3b"
    assert parse_ollama_cli("rm -rf /") is None
    assert parse_ollama_cli("") is None
    assert parse_ollama_cli("ollama list") is None

    print("local_model_catalog ok")


if __name__ == "__main__":
    main()
