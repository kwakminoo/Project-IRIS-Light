"""채팅 제목 라우트: Hermes 켜져 있어도 hermes가 아니다. api: 만 provider API."""

from __future__ import annotations

from unittest.mock import patch

from iris.runtime.backend_route import resolve_title_route
from iris.storage.api_providers import ApiProvider


def main() -> None:
    provider = ApiProvider(
        id="nv1",
        name="NVIDIA",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="sk-test",
        auth_style="bearer",
        models=["nvidia/nemotron-mini"],
    )
    ollama = "http://127.0.0.1:11434/v1"

    with patch(
        "iris.storage.api_providers.get_api_provider", return_value=provider
    ):
        route = resolve_title_route(
            "api:nv1:nvidia/nemotron-mini",
            db=object(),
            ollama_base_url=ollama,
        )
    assert route is not None, "api runtime must resolve"
    assert route.backend == "api", route.backend
    assert route.model == "nvidia/nemotron-mini"
    assert "nvidia.com" in (route.base_url or "")

    # Hermes ON 이어도 제목 라우트는 ollama 직행 (도구 불필요)
    for name in ("qwen3:8b", "gpt-oss:120b-cloud"):
        local = resolve_title_route(name, db=None, ollama_base_url=ollama)
        assert local is not None, name
        assert local.backend == "ollama", (name, local.backend)
        assert local.model == name

    print("chat_title_route self-check ok")


if __name__ == "__main__":
    main()
