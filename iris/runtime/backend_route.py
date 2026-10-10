"""모델 이름 → 어느 백엔드로 어떻게 부를지.

창(MainWindow)과 헤드리스 CLI 가 **같은 규칙**을 써야 한다. 앱이 켜져 있을 때와
꺼져 있을 때 루틴이 다른 모델로 돌면 사용자는 이유를 알 수 없다.

DB(등록된 API 설정)를 읽으므로 워커 스레드가 아니라 호출부에서 먼저 푼다.
"""

from __future__ import annotations

from typing import Any

from iris.ui.workers.backend_call import BackendRoute


def resolve_backend_route(
    settings: Any,
    db: Any,
    model: str,
) -> BackendRoute | None:
    """지금 설정 기준으로 이 모델을 부를 방법. 못 정하면 None.

    Hermes 가 켜져 있으면 Ollama 이름이든 `api:` id 든 전부 게이트웨이를 거친다.
    꺼져 있으면 `api:` id 는 등록된 프로바이더로, 나머지는 Ollama 데몬으로 간다.
    """
    name = str(model or "").strip()
    if not name:
        return None

    if bool(getattr(settings, "hermes_enabled", False)):
        try:
            from iris.infrastructure.hermes_client import resolve_hermes_inference

            target = resolve_hermes_inference(
                name,
                db=db,
                ollama_base_url=getattr(settings, "ollama_base_url", ""),
            )
        except Exception:  # noqa: BLE001
            return None
        return BackendRoute(
            backend="hermes",
            model=name,
            base_url=getattr(settings, "hermes_base_url", ""),
            api_key=getattr(settings, "hermes_api_key", ""),
            command=getattr(settings, "hermes_command", "hermes"),
            target=target,
        )

    from iris.storage.api_providers import get_api_provider, parse_runtime_model_id

    parsed = parse_runtime_model_id(name)
    if parsed is not None:
        provider_id, api_model = parsed
        provider = get_api_provider(db, provider_id) if db is not None else None
        if provider is None or not (getattr(provider, "base_url", "") or "").strip():
            return None
        return BackendRoute(
            backend="api",
            model=api_model,
            base_url=provider.base_url,
            api_key=provider.api_key,
            auth_style=provider.auth_style,
        )

    return BackendRoute(
        backend="ollama",
        model=name,
        base_url=getattr(settings, "ollama_base_url", ""),
    )


def route_for_routine(settings: Any, db: Any, routine: Any, fallback_model: str = ""):
    """루틴이 쓸 경로. 고정 모델이 있으면 그것, 못 쓰면 현재 모델로 물러선다.

    반환: (route 또는 None, 사용자에게 알릴 문구)
    """
    pinned = (getattr(routine, "model", "") or "").strip()
    wanted = pinned or fallback_model
    route = resolve_backend_route(settings, db, wanted)
    if route is not None:
        return route, ""
    if pinned and fallback_model and fallback_model != pinned:
        route = resolve_backend_route(settings, db, fallback_model)
        if route is not None:
            return route, (
                f"지정 모델 '{pinned}' 을 쓸 수 없어 '{fallback_model}' 으로 실행합니다."
            )
    return None, "쓸 모델을 정하지 못했습니다."


def settings_for_model(settings: Any, ollama_base_url: str) -> Any:
    """설정 객체가 없으면 Ollama 주소만 있는 최소 설정을 만든다."""
    if settings is not None:
        return settings
    from types import SimpleNamespace

    return SimpleNamespace(
        hermes_enabled=False,
        ollama_base_url=ollama_base_url or "http://127.0.0.1:11434/v1",
    )


def ask_selected_model(
    settings: Any,
    db: Any,
    model: str,
    prompt: str,
    *,
    system: str = "",
    timeout_sec: float = 120.0,
) -> str:
    """채팅에서 고른 모델로 한 번 묻고 본문만 받는다.

    Ollama 이름, `api:{제공자}:{모델}`, Hermes 경유를 채팅과 같은 규칙으로 보낸다.
    """
    name = str(model or "").strip()
    if not name:
        raise RuntimeError("모델 선택이 필요합니다.")
    route = resolve_backend_route(settings, db, name)
    if route is None:
        raise RuntimeError(
            "선택한 모델로 요청을 보내지 못했습니다. 설정에서 해당 제공자를 확인해 주세요."
        )
    messages: list[dict[str, str]] = []
    if (system or "").strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": prompt})
    from iris.ui.workers.backend_call import collect_reply

    return collect_reply(route, messages, timeout_sec=timeout_sec)


def vision_endpoint(db: Any, model: str, *, ollama_base_url: str) -> dict[str, str]:
    """위키 이미지 읽기. `api:` id 는 그 제공자로, 그 외는 Ollama로."""
    spec = {
        "model": (model or "").strip(),
        "ollama_base_url": (ollama_base_url or "").strip(),
        "api_base_url": "",
        "api_key": "",
        "auth_style": "bearer",
    }
    from iris.storage.api_providers import get_api_provider, parse_runtime_model_id

    parsed = parse_runtime_model_id(spec["model"])
    if parsed is None:
        return spec
    provider = get_api_provider(db, parsed[0]) if db is not None else None
    spec["model"] = parsed[1]
    if provider is not None and (provider.base_url or "").strip():
        spec["api_base_url"] = provider.base_url.strip()
        spec["api_key"] = provider.api_key
        spec["auth_style"] = provider.auth_style or "bearer"
    return spec


if __name__ == "__main__":
    from types import SimpleNamespace

    ollama_only = SimpleNamespace(
        hermes_enabled=False, ollama_base_url="http://127.0.0.1:11434/v1"
    )
    route = resolve_backend_route(ollama_only, None, "qwen3:8b")
    assert route.backend == "ollama" and route.model == "qwen3:8b"
    assert resolve_backend_route(ollama_only, None, "  ") is None

    class _MemDb:
        def __init__(self) -> None:
            self.prefs: dict[str, str] = {}

        def get_preference(self, key: str, default: str = "") -> str:
            return self.prefs.get(key, default)

        def set_preference(self, key: str, value: str) -> None:
            self.prefs[key] = value

    from iris.storage.api_providers import ApiProvider, upsert_api_provider

    mem = _MemDb()
    upsert_api_provider(
        mem,
        ApiProvider(
            id="nid",
            name="NVIDIA NIM",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="secret",
            models=["nvidia/nemotron-3-nano"],
        ),
    )
    route = resolve_backend_route(ollama_only, mem, "api:nid:nvidia/nemotron-3-nano")
    assert route is not None and route.backend == "api"
    assert route.model == "nvidia/nemotron-3-nano"
    assert route.base_url == "https://integrate.api.nvidia.com/v1"
    assert resolve_backend_route(ollama_only, mem, "api:missing:foo") is None
    seen = vision_endpoint(mem, "api:nid:nvidia/nemotron-3-nano", ollama_base_url="http://127.0.0.1:11434/v1")
    assert seen["model"] == "nvidia/nemotron-3-nano"
    assert seen["api_base_url"] == "https://integrate.api.nvidia.com/v1"
    assert vision_endpoint(None, "qwen3:8b", ollama_base_url="http://127.0.0.1:11434/v1")["api_base_url"] == ""

    # Hermes 가 켜져 있으면 전부 게이트웨이로
    hermes_on = SimpleNamespace(
        hermes_enabled=True,
        hermes_base_url="http://127.0.0.1:8642/v1",
        hermes_api_key="k",
        hermes_command="hermes",
        ollama_base_url="http://127.0.0.1:11434/v1",
    )

    import iris.infrastructure.hermes_client as hc

    original = hc.resolve_hermes_inference
    hc.resolve_hermes_inference = lambda m, **kw: SimpleNamespace(model=f"up/{m}", label=m)
    try:
        route = resolve_backend_route(hermes_on, None, "qwen3:8b")
        assert route.backend == "hermes" and route.target.model == "up/qwen3:8b"
        assert route.api_key == "k"

        # 해석이 실패하면 None
        hc.resolve_hermes_inference = lambda m, **kw: (_ for _ in ()).throw(ValueError("없음"))
        assert resolve_backend_route(hermes_on, None, "api:gone:x") is None
    finally:
        hc.resolve_hermes_inference = original

    # 루틴 고정 모델
    pinned = SimpleNamespace(model="qwen3:32b")
    route, note = route_for_routine(ollama_only, None, pinned, "gemma4:free")
    assert route.model == "qwen3:32b" and note == ""

    unpinned = SimpleNamespace(model="")
    route, note = route_for_routine(ollama_only, None, unpinned, "gemma4:free")
    assert route.model == "gemma4:free" and note == ""

    # 아무 모델도 없으면 솔직히 실패
    route, note = route_for_routine(ollama_only, None, unpinned, "")
    assert route is None and "정하지 못했" in note

    print("backend_route self-check ok")
