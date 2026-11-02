"""백엔드 한 번 호출해서 답만 걷어오기 — 워커들이 공유한다.

인수인계문 요약도, 루틴 실행도 결국 "이 모델에 이 messages 를 보내고 텍스트를
받아라"는 같은 일이다. 다른 점은 무엇을 물어보고 결과를 어디에 쓰느냐뿐이라
호출 자체는 여기 한 군데 둔다.

어느 백엔드로 갈지는 **UI 스레드가 정해서** `BackendRoute` 에 담아 넘긴다.
해석에 DB(등록된 API 설정)가 필요하기 때문에 워커가 직접 고르면 안 된다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

BACKEND_OLLAMA = "ollama"
BACKEND_HERMES = "hermes"
BACKEND_API = "api"

DEFAULT_TIMEOUT_SEC = 90.0


@dataclass
class BackendRoute:
    """어디로 보낼지. 비밀값이 들어오므로 로그에 통째로 찍지 않는다."""

    backend: str
    model: str
    base_url: str = ""
    api_key: str = ""
    auth_style: str = "bearer"
    command: str = "hermes"
    # Hermes 전용 — resolve_hermes_inference() 결과
    target: Any = None
    extra: dict[str, str] = field(default_factory=dict)


def collect_reply(
    route: BackendRoute,
    messages: list[dict[str, str]],
    *,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    cancelled: Callable[[], bool] | None = None,
    think: bool = False,
) -> str:
    """스트림을 끝까지 받아 본문만 이어 붙인다."""
    stop = cancelled or (lambda: False)
    backend = (route.backend or "").strip().lower()
    if backend == BACKEND_HERMES:
        return _hermes(route, messages, stop)
    if backend == BACKEND_API:
        return _api(route, messages, timeout_sec, stop)
    return _ollama(route, messages, timeout_sec, stop, think)


def _ollama(route, messages, timeout_sec, stop, think) -> str:
    from iris.infrastructure.ollama_client import OllamaClient

    client = OllamaClient(
        route.base_url or "http://127.0.0.1:11434/v1", timeout_sec=timeout_sec
    )
    parts: list[str] = []
    for ev in client.stream_chat(route.model, messages, think=think):
        if stop():
            break
        chunk = ev.get("content")
        if isinstance(chunk, str) and chunk:
            parts.append(chunk)
        if ev.get("done"):
            break
    return "".join(parts)


def _hermes(route, messages, stop) -> str:
    from iris.infrastructure.hermes_client import HermesClient

    client = HermesClient(
        route.base_url or "http://127.0.0.1:8642/v1",
        api_key=route.api_key,
        command=route.command,
    )
    # 채팅 워커와 같다. 설정 칸을 덮지 않고, provider가 있을 때만 넘긴다.
    target = route.target
    if target is not None:
        model = target.model
        provider = str(getattr(target, "provider", "") or "").strip()
        base_url = str(getattr(target, "base_url", "") or "").strip()
        synced = False
        try:
            client.set_inference_model(target.model, target=target)
            synced = True
        except Exception:
            synced = False
        # Sync 실패 + custom endpoint면 Hermes 레지스트리 404를 피하고 제공자로 직행.
        if not synced and base_url and provider == "custom":
            return _api(
                BackendRoute(
                    backend=BACKEND_API,
                    model=model,
                    base_url=base_url,
                    api_key=str(getattr(target, "api_key", "") or ""),
                    auth_style="bearer",
                ),
                messages,
                DEFAULT_TIMEOUT_SEC,
                stop,
            )
    else:
        model = route.model
        provider = ""
    stream_kwargs = {"provider": provider} if provider else {}
    parts: list[str] = []
    for ev in client.stream_chat(model, messages, **stream_kwargs):
        if stop():
            break
        chunk = ev.get("content")
        if isinstance(chunk, str) and chunk:
            parts.append(chunk)
        if ev.get("done"):
            break
    return "".join(parts)


def _api(route, messages, timeout_sec, stop) -> str:
    from iris.infrastructure.openai_compat_client import stream_chat

    parts: list[str] = []
    for ev in stream_chat(
        route.base_url,
        route.api_key,
        route.model,
        messages,
        auth_style=route.auth_style,
        timeout=timeout_sec,
    ):
        if stop():
            break
        chunk = ev.get("content")
        if isinstance(chunk, str) and chunk:
            parts.append(chunk)
        if ev.get("done"):
            break
    return "".join(parts)


if __name__ == "__main__":
    r = BackendRoute(backend="ollama", model="m")
    assert r.base_url == "" and r.target is None and r.extra == {}
    assert BackendRoute(backend="api", model="m", auth_style="x-api-key").auth_style == "x-api-key"

    class _FakeTarget:
        model = "nvidia/test-model"
        provider = "custom"
        base_url = "https://example.test/v1"
        api_key = "k"

    class _FakeHermes:
        def __init__(self, *a, **k):
            self.synced = None

        def set_inference_model(self, model, *, target=None, **k):
            self.synced = (model, target)

        def stream_chat(self, model, messages, **k):
            yield {"content": "ok", "done": True}

    class _FailSyncHermes:
        def __init__(self, *a, **k):
            pass

        def set_inference_model(self, model, *, target=None, **k):
            raise RuntimeError("sync failed")

        def stream_chat(self, model, messages, **k):
            raise AssertionError("hermes stream must not run after sync fail + base_url")

    import iris.infrastructure.hermes_client as _hc
    import iris.infrastructure.openai_compat_client as _oc

    fake = _FakeHermes()
    _orig = _hc.HermesClient
    _hc.HermesClient = lambda *a, **k: fake  # type: ignore[misc, assignment]
    try:
        out = collect_reply(
            BackendRoute(backend=BACKEND_HERMES, model="ignored", target=_FakeTarget()),
            [{"role": "user", "content": "hi"}],
        )
    finally:
        _hc.HermesClient = _orig
    assert out == "ok"
    assert fake.synced is not None
    assert fake.synced[0] == "nvidia/test-model"
    assert fake.synced[1] is not None
    assert fake.synced[1].model == "nvidia/test-model"

    _hc.HermesClient = lambda *a, **k: _FailSyncHermes()  # type: ignore[misc, assignment]
    _orig_stream = _oc.stream_chat

    def _fake_api_stream(*a, **k):
        yield {"content": "via-api", "done": True}

    _oc.stream_chat = _fake_api_stream  # type: ignore[assignment]
    try:
        out2 = collect_reply(
            BackendRoute(backend=BACKEND_HERMES, model="ignored", target=_FakeTarget()),
            [{"role": "user", "content": "hi"}],
        )
    finally:
        _hc.HermesClient = _orig
        _oc.stream_chat = _orig_stream
    assert out2 == "via-api"
    print("backend_call self-check ok")
