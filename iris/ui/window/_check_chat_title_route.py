"""채팅 제목/요약 라우트: Hermes 켜져 있어도 Iris API 모델은 backend=api."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from iris.storage.api_providers import ApiProvider
from iris.ui.window.main_window import MainWindow


def main() -> None:
    provider = ApiProvider(
        id="nv1",
        name="NVIDIA",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="sk-test",
        auth_style="bearer",
        models=["nvidia/nemotron-mini"],
    )
    win = MagicMock()
    win._use_hermes_backend = lambda: True
    win._db = object()
    win._settings = SimpleNamespace(
        ollama_base_url="http://127.0.0.1:11434/v1",
        hermes_base_url="http://127.0.0.1:8642/v1",
        hermes_api_key="hk",
        hermes_command="hermes",
    )

    with patch(
        "iris.ui.window.main_window.get_api_provider", return_value=provider
    ):
        route = MainWindow._summary_route_for(
            win, "api:nv1:nvidia/nemotron-mini"
        )
    assert route is not None, "api runtime must resolve"
    assert route.backend == "api", route.backend
    assert route.model == "nvidia/nemotron-mini"
    assert "nvidia.com" in (route.base_url or "")

    with patch(
        "iris.infrastructure.hermes_client.resolve_hermes_inference",
        return_value=SimpleNamespace(model="qwen3:8b", provider="custom"),
    ):
        local = MainWindow._summary_route_for(win, "qwen3:8b")
    assert local is not None and local.backend == "hermes", local

    print("chat_title_route self-check ok")


if __name__ == "__main__":
    main()
