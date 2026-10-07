"""화면을 '볼 수 있는' 로컬 모델 고르기·받기 — 모니터링과 업무 학습이 같이 쓴다.

채팅 모델(gemma4 등)은 Ollama에 vision 능력이 등록돼 있지 않으면 이미지를
조용히 무시하고 창 제목만 보고 답한다. 그래서 화면 분석에는 vision 능력이
확인된 모델만 쓴다. 기본은 `qwen2.5vl:3b`(약 3GB) — 6GB GPU에 올라가고
한국어 화면 글자도 읽는다. 사용자가 기능을 처음 쓸 때 동의를 받고 받는다.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from iris.infrastructure.ollama_client import OllamaClient, _native_base

DEFAULT_VISION_MODEL = "qwen2.5vl:3b"
DEFAULT_VISION_MODEL_SIZE_GB = 3.2
# 화면 분석 호출의 컨텍스트 — 기본값이면 6GB GPU 에서 CPU 로 밀려 수십 배 느려진다
VISION_NUM_CTX = 4096

_CACHE_TTL_SEC = 120.0
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Optional[str], str]] = {}


def preferred_vision_model() -> str:
    """IRIS_VISION_MODEL 로 바꿀 수 있다 (예: qwen2.5vl:7b)."""
    return os.environ.get("IRIS_VISION_MODEL", "").strip() or DEFAULT_VISION_MODEL


def _same_model(a: str, b: str) -> bool:
    def norm(n: str) -> str:
        n = (n or "").strip().lower()
        return n if ":" in n else f"{n}:latest"

    return norm(a) == norm(b)


def _has_vision(client: OllamaClient, name: str) -> bool:
    """/api/show capabilities 로만 판정 — 이름 추측은 gemma4 처럼 틀린다."""
    try:
        data = client.show_model(name, timeout_sec=10.0)
    except Exception:
        return False
    caps = {str(c).lower() for c in (data or {}).get("capabilities") or []}
    return "vision" in caps


def resolve_vision_model(
    client: OllamaClient, chat_model: str = "", *, use_cache: bool = True
) -> tuple[Optional[str], str]:
    """(쓸 모델, 사유). 없으면 (None, 사용자에게 보여줄 사유).

    우선순위: 기본 vision 모델 설치됨 → 채팅 모델이 vision 지원 → 없음.
    """
    key = f"{client.base_url}|{chat_model}"
    now = time.monotonic()
    if use_cache:
        with _cache_lock:
            hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL_SEC:
            return hit[1], hit[2]

    preferred = preferred_vision_model()
    try:
        installed = [m.name for m in client.list_models() if not m.is_cloud]
    except Exception as e:
        result: tuple[Optional[str], str] = (None, f"Ollama에 연결하지 못했어요 ({e})")
        with _cache_lock:
            _cache.pop(key, None)  # 연결 실패는 캐시하지 않는다 — 다음 주기에 다시 본다
        return result

    if any(_same_model(n, preferred) for n in installed):
        result = (preferred, "")
    else:
        chat = (chat_model or "").strip()
        local_chat = next((n for n in installed if _same_model(n, chat)), "") if chat else ""
        if local_chat and _has_vision(client, local_chat):
            result = (local_chat, "")
        else:
            result = (
                None,
                f"화면을 볼 수 있는 모델이 없어요 — {preferred}"
                f"(약 {DEFAULT_VISION_MODEL_SIZE_GB:.0f}GB) 설치가 필요해요.",
            )
    with _cache_lock:
        _cache[key] = (now, result[0], result[1])
    return result


def forget_cache() -> None:
    with _cache_lock:
        _cache.clear()


def pull_model(
    base_url: str,
    model: str,
    on_progress: Callable[[str, Optional[int]], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> Optional[str]:
    """Ollama /api/pull 스트리밍. 성공이면 None, 실패면 사유."""
    url = f"{_native_base(base_url)}/api/pull"
    body = json.dumps({"model": model, "stream": True}).encode("utf-8")
    req = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    last_pct: Optional[int] = None
    try:
        with urlopen(req, timeout=3600) as resp:
            while True:
                if should_abort and should_abort():
                    return "중단했어요"
                raw = resp.readline()
                if not raw:
                    break
                try:
                    ev = json.loads(raw.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(ev, dict):
                    continue
                if ev.get("error"):
                    return str(ev["error"])[:200]
                total = int(ev.get("total") or 0)
                done = int(ev.get("completed") or 0)
                pct = int(100 * done / total) if total > 0 else None
                if on_progress and (pct != last_pct or pct is None):
                    on_progress(str(ev.get("status") or ""), pct)
                    last_pct = pct
    except (URLError, TimeoutError, OSError) as e:
        return str(e)[:200]
    forget_cache()
    return None


_KEEP_ALIVE = "30m"  # 다시 올리는 데 80~100초 걸린다 (이 PC 실측) — 한 번 올리면 붙잡아 둔다


def is_garbage(text: str) -> bool:
    """qwen2.5vl 이 Ollama 에서 가끔 '@@@@…'만 돌려준다 (컨텍스트·메모리 상태 따라)."""
    t = (text or "").strip()
    return len(t) >= 6 and t.count("@") / len(t) > 0.5


def unload(base_url: str, model: str) -> None:
    try:
        body = json.dumps({"model": model, "keep_alive": 0}).encode("utf-8")
        req = Request(f"{_native_base(base_url)}/api/generate", data=body, method="POST",
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            resp.read()
    except Exception:
        pass


def vision_chat(
    client: OllamaClient,
    model: str,
    prompt: str,
    images_png: list[bytes],
    *,
    system: str = "",
    timeout_sec: float = 180.0,
) -> str:
    """화면 분석 호출은 모두 여기로 — 같은 num_ctx(다르면 모델을 다시 올린다)와
    keep_alive 를 쓰고, '@@@@' 가 오면 모델을 내렸다 올려 한 번 더 묻는다."""
    for attempt in range(2):
        text = client.chat_once_with_images(
            model, prompt, images_png, system=system, timeout_sec=timeout_sec,
            num_ctx=VISION_NUM_CTX, keep_alive=_KEEP_ALIVE,
        )
        if not is_garbage(text):
            return text
        if attempt == 0:
            unload(client.base_url, model)
    return ""
