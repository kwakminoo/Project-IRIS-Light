"""Ollama HTTP 클라이언트 — 모델 목록·채팅 스트림(thinking 포함)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

OLLAMA_CLOUD_CATALOG_URL = "https://ollama.com/api/tags"


@dataclass(frozen=True)
class OllamaModelInfo:
    """catalog_name: UI 표시, name: 로컬 Ollama API용 런타임 이름."""

    name: str
    catalog_name: str = ""
    size: int = 0
    digest: str = ""
    # probe 전/실패 시 True — 숨기지 않고 기본(도구 지원) 스타일로 표시
    supports_tools: bool = True
    requires_subscription: bool = False
    # 커스텀 API 전용 3-상태 (yes|no|unknown). 빈 문자열이면 supports_tools를 씀
    tool_support: str = ""
    # 모델 정리 결과. ok | unverified | unavailable | ""
    availability: str = ""
    # 커스텀 API Base URL. 로컬 피커 분류용. Ollama 모델은 비움.
    endpoint: str = ""

    def __post_init__(self) -> None:
        if not self.catalog_name:
            object.__setattr__(self, "catalog_name", display_name_from_runtime(self.name))

    @property
    def is_cloud(self) -> bool:
        n = self.name.lower()
        return n.endswith("-cloud") or ":cloud" in n or n.endswith(":cloud")


def probe_status_from_http_detail(detail: str) -> str:
    """probe HTTP 본문 → 'ok' | 'subscription' | 'unavailable'."""
    text = (detail or "").lower()
    if "subscription" in text or "upgrade" in text:
        return "subscription"
    if "not found" in text:
        return "unavailable"
    return "unavailable"


def cleanup_verdict(
    status: str,
    *,
    transient: bool,
    capabilities: list[str] | None,
    show_ok: bool,
) -> tuple[str, str]:
    """모델 정리 판정 — (state, tool_support).

    state: ok | unverified | unavailable. tool: yes | no | unknown.
    타임아웃·429·5xx는 unverified라 목록에 남긴다. 구독 전용·대화 거부는 제외.
    """
    if transient:
        return "unverified", "unknown"
    if status != "ok":
        return "unavailable", "unknown"
    if not show_ok:
        return "ok", "unknown"
    return "ok", ("yes" if supports_tools_capability(capabilities) else "no")


def apply_ollama_cleanup(
    model: OllamaModelInfo, record: dict[str, str] | None
) -> OllamaModelInfo:
    """저장된 정리 결과. 거절된 모델도 목록에 남기고 availability 만 채운다."""
    if not record:
        return model
    state = str(record.get("state") or "")
    tool = str(record.get("tool") or "")
    if tool not in ("yes", "no", "unknown"):
        tool = model.tool_support or "unknown"
    return OllamaModelInfo(
        name=model.name,
        catalog_name=model.catalog_name,
        size=model.size,
        digest=model.digest,
        supports_tools=tool != "no",
        requires_subscription=model.requires_subscription,
        tool_support=tool,
        availability=state,
        endpoint=model.endpoint,
    )


def model_list_tier(name: str, *, state: str = "", tool: str = "") -> tuple[int, str]:
    """피커 정렬. 0 쓸 수 있음, 1 쓸 수 없음, 2 적합하지 않음."""
    bare = (name or "").strip()
    if bare.lower().startswith("api:") and bare.count(":") >= 2:
        bare = bare.split(":", 2)[2]
    if is_embedding_model_name(bare) or tool == "no":
        return 2, "적합하지 않음"
    if state == "unavailable":
        return 1, "쓸 수 없음"
    return 0, "쓸 수 있음"


def roster_summary(names: list[str], states: dict[str, str], tools: dict[str, str]) -> str:
    """설정 화면용. 세 묶음으로 이름을 적는다."""
    buckets: dict[int, list[str]] = {0: [], 1: [], 2: []}
    titles = {0: "쓸 수 있는 모델", 1: "쓸 수 없는 모델", 2: "적합하지 않은 모델"}
    for name in names:
        rank, _label = model_list_tier(
            name, state=str(states.get(name) or ""), tool=str(tools.get(name) or "")
        )
        buckets[rank].append(name)
    lines = []
    for rank in (0, 1, 2):
        if buckets[rank]:
            lines.append(titles[rank] + ": " + ", ".join(buckets[rank]))
    return "\n".join(lines)


def display_name_from_runtime(runtime_name: str) -> str:
    """UI용 짧은 모델명.

    - ``api:{provider_id}:{model}`` → 모델명만
    - ``google/gemma-…`` / ``models/gemini-…`` → 경로·org 제거
    - ``gemma4:31b-cloud`` → ``gemma4:31b``
    - 하이픈 구분 API id → 공백 (``gemini-2.5-flash`` → ``gemini 2.5 flash``)
    """
    n = (runtime_name or "").strip()
    if not n or n == "(unset)":
        return n
    # Iris 커스텀 API runtime — provider id 버리고 모델 id만
    if n.lower().startswith("api:") and ":" in n[4:]:
        n = n.split(":", 2)[2].strip()
    for suf in ("-cloud", ":cloud"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    # org/models/… 경로 → 마지막 세그먼트
    if "/" in n:
        n = n.rsplit("/", 1)[-1].strip()
    if not n:
        return runtime_name.strip()
    # Ollama 태그(gemma4:31b)는 그대로
    if ":" in n:
        return n
    # API 스타일 하이픈 id → 읽기 쉬운 공백
    return n.replace("-", " ").strip()


def to_runtime_cloud_name(catalog_name: str) -> str:
    """
    ollama.com 카탈로그 이름 → 로컬 daemon용 클라우드 모델 ID.
    예: gemma4:31b → gemma4:31b-cloud, minimax-m3 → minimax-m3:cloud
    """
    name = catalog_name.strip()
    if not name:
        return name
    if name.endswith("-cloud") or name.endswith(":cloud"):
        return name
    if re.search(r":\d+(?:\.\d+)?[a-z]*$", name, re.IGNORECASE):
        return f"{name}-cloud"
    return f"{name}:cloud"


def supports_tools_capability(capabilities: list[str] | None) -> bool:
    """Ollama capabilities 목록에 'tools'가 있으면 도구 호출 가능."""
    return "tools" in (capabilities or [])


def _native_base(openai_or_native: str) -> str:
    """http://host:11434/v1 → http://host:11434"""
    raw = (openai_or_native or "").strip().rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw or "http://127.0.0.1:11434"


# 임베딩 전용 모델 — Ollama는 용도를 알려주는 API가 없어 이름으로 가른다.
# 앞일수록 한국어 품질이 좋아 우선 선택된다.
EMBEDDING_MODEL_PREFERENCE: tuple[str, ...] = (
    "bge-m3",
    "qwen3-embedding",
    "multilingual-e5",
    "mxbai-embed-large",
    "snowflake-arctic-embed2",
    "nomic-embed-text",
    "all-minilm",
)
_EMBEDDING_NAME_HINTS = ("embed", "bge-", "e5-", "gte-")


def is_embedding_model_name(name: str) -> bool:
    """`bge-m3:latest`·`nomic-embed-text` 처럼 임베딩 전용인지 이름으로 판별."""
    base = (name or "").strip().lower().split(":")[0]
    if not base:
        return False
    if any(base == p or base.startswith(f"{p}-") or base.startswith(f"{p}:") for p in EMBEDDING_MODEL_PREFERENCE):
        return True
    return any(hint in base for hint in _EMBEDDING_NAME_HINTS)


def embedding_model_rank(name: str) -> tuple[int, str]:
    """선호 목록 순서 → 정렬 키. 목록에 없으면 뒤로."""
    base = (name or "").strip().lower().split(":")[0]
    for idx, pref in enumerate(EMBEDDING_MODEL_PREFERENCE):
        if base == pref or base.startswith(f"{pref}-"):
            return (idx, base)
    return (len(EMBEDDING_MODEL_PREFERENCE), base)


def host_label_for_model(model: str, base_url: str) -> str:
    """터미널 Connecting 메시지용 호스트 라벨."""
    if OllamaModelInfo(name=model).is_cloud:
        return "ollama.com"
    try:
        netloc = urlparse(_native_base(base_url)).netloc
        return netloc or "localhost"
    except Exception:
        return "localhost"


class OllamaClient:
    """로컬 Ollama daemon + ollama.com 클라우드 카탈로그."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", timeout_sec: float = 300.0) -> None:
        self.base_url = _native_base(base_url)
        self.timeout_sec = timeout_sec

    def list_models(self) -> list[OllamaModelInfo]:
        data = self._get_json("/api/tags")
        out: list[OllamaModelInfo] = []
        for m in data.get("models") or []:
            name = str(m.get("name") or "").strip()
            if not name:
                continue
            out.append(
                OllamaModelInfo(
                    name=name,
                    size=int(m.get("size") or 0),
                    digest=str(m.get("digest") or ""),
                )
            )
        out.sort(key=lambda x: (not x.is_cloud, x.catalog_name.lower()))
        return out

    def list_cloud_catalog(self) -> list[OllamaModelInfo]:
        """ollama.com 공식 클라우드 카탈로그 (무료·Pro 포함 전체)."""
        try:
            data = self._get_json_url(OLLAMA_CLOUD_CATALOG_URL)
        except Exception:
            return self._local_cloud_fallback()

        out: list[OllamaModelInfo] = []
        seen: set[str] = set()
        for m in data.get("models") or []:
            catalog = str(m.get("name") or "").strip()
            if not catalog:
                continue
            runtime = to_runtime_cloud_name(catalog)
            if runtime in seen:
                continue
            seen.add(runtime)
            out.append(
                OllamaModelInfo(
                    name=runtime,
                    catalog_name=catalog,
                    size=int(m.get("size") or 0),
                    digest=str(m.get("digest") or ""),
                )
            )
        out.sort(key=lambda x: x.catalog_name.lower())
        return out if out else self._local_cloud_fallback()

    def list_free_cloud_models(
        self, *, probe: bool = True, tools_only: bool = False, max_workers: int = 6
    ) -> list[OllamaModelInfo]:
        """
        클라우드 카탈로그 모델을 반환하고, probe 시 구독/도구 지원 플래그를 채운다.
        tools_only=True면 예전처럼 무료+도구 지원만 남긴다(하위 호환).
        probe=False면 카탈로그 전체(플래그 기본값) 반환.
        """
        catalog = self.list_cloud_catalog()
        if not probe or not catalog:
            return catalog

        def _classify(model: OllamaModelInfo) -> OllamaModelInfo | None:
            status = self.probe_model_status(model.name)
            requires_sub = status == "subscription"
            # 조회 실패(unavailable)도 목록에는 남긴다 — 색/경고만 다르게.
            tools = True
            if status in ("ok", "subscription"):
                tools = self.model_supports_tools(model.name)
            if tools_only and (requires_sub or not tools):
                return None
            return OllamaModelInfo(
                name=model.name,
                catalog_name=model.catalog_name,
                size=model.size,
                digest=model.digest,
                supports_tools=tools,
                requires_subscription=requires_sub,
            )

        classified: list[OllamaModelInfo] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_classify, m): m for m in catalog}
            for fut in as_completed(futures):
                try:
                    item = fut.result()
                except Exception:
                    item = futures[fut]
                if item is not None:
                    classified.append(item)
        classified.sort(key=lambda x: x.catalog_name.lower())
        return classified if classified else catalog
    def show_model(self, runtime_name: str, *, timeout_sec: float = 15.0) -> dict[str, Any]:
        """POST /api/show — capabilities·model_info."""
        payload = {"model": runtime_name}
        req = Request(
            f"{self.base_url}/api/show",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, dict) else {}
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            return {}

    def model_context_length(self, runtime_name: str, *, default: int = 128_000) -> int:
        """모델 컨텍스트 윈도우 토큰 수 (/api/show model_info)."""
        data = self.show_model(runtime_name)
        info = data.get("model_info") if isinstance(data.get("model_info"), dict) else {}
        for key, val in info.items():
            if str(key).endswith(".context_length"):
                try:
                    n = int(val)
                    if n > 0:
                        return n
                except (TypeError, ValueError):
                    continue
        return default

    def model_supports_tools(self, runtime_name: str, *, timeout_sec: float = 15.0) -> bool:
        """Ollama /api/show capabilities에 'tools'가 있으면 True.
        조회 실패 시엔 관대하게 True — 일시적 오류로 모델을 임의로 숨기지 않는다."""
        data = self.show_model(runtime_name, timeout_sec=timeout_sec)
        if not data:
            return True  # ponytail: 조회 실패는 배제 근거로 삼지 않음
        return supports_tools_capability(data.get("capabilities"))


    def probe_model_outcome(
        self, runtime_name: str, *, timeout_sec: float = 25.0
    ) -> tuple[str, bool]:
        """(status, transient). transient면 네트워크·과부하 — 모델 탓으로 빼지 않음."""
        payload = {
            "model": runtime_name,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        }
        req = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout_sec) as resp:
                json.loads(resp.read().decode("utf-8"))
            return "ok", False
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            status = probe_status_from_http_detail(detail)
            code = int(e.code)
            if status == "subscription":
                return status, False
            if code in (401, 429) or code >= 500:
                return "unavailable", True
            return status, False
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            return "unavailable", True

    def probe_model_status(self, runtime_name: str, *, timeout_sec: float = 25.0) -> str:
        """'ok' | 'subscription' | 'unavailable'."""
        status, _transient = self.probe_model_outcome(runtime_name, timeout_sec=timeout_sec)
        return status

    def classify_model(self, runtime_name: str, *, timeout_sec: float = 25.0) -> tuple[str, str]:
        """모델 정리 1건 — (state, tool_support)."""
        status, transient = self.probe_model_outcome(runtime_name, timeout_sec=timeout_sec)
        if transient or status != "ok":
            return cleanup_verdict(
                status, transient=transient, capabilities=None, show_ok=False
            )
        data = self.show_model(runtime_name)
        caps = data.get("capabilities") if isinstance(data.get("capabilities"), list) else None
        return cleanup_verdict(
            status, transient=False, capabilities=caps, show_ok=bool(data)
        )

    def probe_model_available(self, runtime_name: str, *, timeout_sec: float = 25.0) -> bool:
        """구독 없이 호출 가능하면 True (무료 tier 포함)."""
        return self.probe_model_status(runtime_name, timeout_sec=timeout_sec) == "ok"

    def _local_cloud_fallback(self) -> list[OllamaModelInfo]:
        models = self.list_models()
        cloud = [m for m in models if m.is_cloud]
        return cloud if cloud else models

    def list_cloud_preferring(self) -> list[OllamaModelInfo]:
        """하위 호환 — 클라우드 카탈로그(+probe 분류)."""
        return self.list_free_cloud_models(probe=True)

    def list_chat_models(self, *, probe_cloud: bool = True) -> list[OllamaModelInfo]:
        """로컬 설치 모델 + 클라우드 카탈로그 병합 (로컬 우선). Hermes/Ollama 공용."""
        local = self.list_models()
        cloud = self.list_free_cloud_models(probe=probe_cloud, tools_only=False)
        seen: set[str] = set()
        out: list[OllamaModelInfo] = []
        for m in [*local, *cloud]:
            if m.name in seen:
                continue
            seen.add(m.name)
            out.append(m)
        return out
    def list_embedding_models(self) -> list[str]:
        """로컬에 설치된 임베딩 모델만 — 이름으로 판별(별도 API 없음)."""
        try:
            local = self.list_models()
        except Exception:
            return []
        return [m.name for m in local if is_embedding_model_name(m.name)]

    def pick_embedding_model(self, preferred: str = "") -> str:
        """선호 모델 → 설치된 것 중 품질순. 없으면 빈 문자열(키워드 검색만 씀)."""
        installed = self.list_embedding_models()
        if not installed:
            return ""
        want = (preferred or "").strip()
        if want:
            for name in installed:
                if name == want or name.split(":")[0] == want.split(":")[0]:
                    return name
        ranked = sorted(installed, key=embedding_model_rank)
        return ranked[0]

    def embed(
        self,
        model: str,
        texts: list[str],
        *,
        timeout_sec: float = 120.0,
        keep_alive: str | None = None,
    ) -> list[list[float]]:
        """텍스트 배치 → 벡터. 신형 /api/embed, 실패 시 구형 /api/embeddings 폴백.

        `keep_alive` — 모델을 메모리에 붙잡아 둘 시간("30m"). Ollama는 요청마다
        만료 시각을 그 요청 값(기본 5분)으로 다시 잡으므로 일관되게 넘겨야 한다.
        """
        items = [str(t or "") for t in texts]
        if not items or not (model or "").strip():
            return []
        extra = {"keep_alive": keep_alive} if keep_alive else {}
        try:
            data = self._post_json(
                "/api/embed",
                {"model": model, "input": items, **extra},
                timeout_sec=timeout_sec,
            )
            vectors = data.get("embeddings")
            if isinstance(vectors, list) and len(vectors) == len(items):
                return [[float(x) for x in vec] for vec in vectors]
        except RuntimeError:
            pass
        # 구형 데몬 — 한 건씩만 받는다
        out: list[list[float]] = []
        for text in items:
            data = self._post_json(
                "/api/embeddings",
                {"model": model, "prompt": text, **extra},
                timeout_sec=timeout_sec,
            )
            vec = data.get("embedding")
            if not isinstance(vec, list):
                raise RuntimeError(f"Ollama 임베딩 응답 형식 오류: {model}")
            out.append([float(x) for x in vec])
        return out

    def stream_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        think: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """
        /api/chat NDJSON 스트림.
        yield: {"thinking": str|None, "content": str|None, "done": bool, "raw": dict}
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": think,
        }
        from iris.runtime.attachment_context import trace_payload
        trace_payload("ollama", payload)
        req = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = obj.get("message") or {}
                    yield {
                        "thinking": msg.get("thinking") if isinstance(msg, dict) else None,
                        "content": msg.get("content") if isinstance(msg, dict) else None,
                        "done": bool(obj.get("done")),
                        "raw": obj,
                    }
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail or e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Ollama 연결 실패: {e.reason}") from e

    def chat_once_with_images(
        self,
        model: str,
        prompt: str,
        images_png: list[bytes],
        *,
        system: str = "",
        timeout_sec: float = 90.0,
    ) -> str:
        """멀티모달 단발 호출 — 스트림 없이 최종 content만 반환.

        이미지는 /api/chat의 messages[].images (base64 PNG)로 보낸다.
        모델이 멀티모달이 아니면 이미지를 무시하고 텍스트만 보므로,
        호출 측에서 결과가 쓸모없을 수 있음을 감안해야 한다.
        """
        import base64

        message: dict[str, Any] = {"role": "user", "content": prompt}
        if images_png:
            message["images"] = [
                base64.b64encode(png).decode("ascii") for png in images_png if png
            ]
        messages: list[dict[str, Any]] = []
        if system.strip():
            messages.append({"role": "system", "content": system.strip()})
        messages.append(message)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
        }
        req = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout_sec) as resp:
                obj = json.loads(resp.read().decode("utf-8", errors="replace"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail or e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Ollama 연결 실패: {e.reason}") from e
        msg = obj.get("message") or {}
        return str(msg.get("content") or "") if isinstance(msg, dict) else ""

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_sec: float = 60.0,
    ) -> dict[str, Any]:
        req = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        try:
            with urlopen(req, timeout=min(timeout_sec, self.timeout_sec)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail or e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Ollama 연결 실패: {e.reason}") from e

    def _get_json(self, path: str) -> dict[str, Any]:
        return self._get_json_url(f"{self.base_url}{path}")

    def _get_json_url(self, url: str) -> dict[str, Any]:
        req = Request(url, method="GET")
        api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        try:
            with urlopen(req, timeout=min(30.0, self.timeout_sec)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Ollama HTTP {e.code}: {detail or e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Ollama 연결 실패: {e.reason}") from e


if __name__ == "__main__":
    # 도구 지원·구독 분류 핵심 로직 자체 점검(네트워크 불필요).
    assert supports_tools_capability(["completion", "tools", "thinking"]) is True
    assert supports_tools_capability(["completion", "vision"]) is False
    assert supports_tools_capability([]) is False
    assert supports_tools_capability(None) is False
    assert probe_status_from_http_detail("requires a subscription to use") == "subscription"
    assert probe_status_from_http_detail("please upgrade your plan") == "subscription"
    assert probe_status_from_http_detail("model not found") == "unavailable"
    assert cleanup_verdict("ok", transient=True, capabilities=["tools"], show_ok=True) == (
        "unverified",
        "unknown",
    )
    assert cleanup_verdict("subscription", transient=False, capabilities=None, show_ok=False) == (
        "unavailable",
        "unknown",
    )
    assert cleanup_verdict("ok", transient=False, capabilities=["tools"], show_ok=True) == (
        "ok",
        "yes",
    )
    assert cleanup_verdict("ok", transient=False, capabilities=["completion"], show_ok=True) == (
        "ok",
        "no",
    )
    kept = apply_ollama_cleanup(OllamaModelInfo(name="a"), {"state": "ok", "tool": "no"})
    assert kept.supports_tools is False and kept.tool_support == "no"
    dead = apply_ollama_cleanup(OllamaModelInfo(name="dead"), {"state": "unavailable"})
    assert dead.availability == "unavailable" and dead.name == "dead"
    assert model_list_tier("gemma:7b", state="ok", tool="yes") == (0, "쓸 수 있음")
    assert model_list_tier("gemma:7b", state="unavailable", tool="unknown") == (1, "쓸 수 없음")
    assert model_list_tier("bge-m3:latest", state="ok", tool="yes")[0] == 2
    assert model_list_tier("qwen:7b", state="ok", tool="no")[0] == 2
    m = OllamaModelInfo(name="x:cloud", supports_tools=False, requires_subscription=True)
    assert m.supports_tools is False and m.requires_subscription is True
    assert display_name_from_runtime("gemma4:31b-cloud") == "gemma4:31b"
    assert display_name_from_runtime("api:ab12:models/gemini-2.5-flash") == "gemini 2.5 flash"
    assert display_name_from_runtime("api:nv:google/gemma-2-9b-it") == "gemma 2 9b it"
    assert display_name_from_runtime("api:x:meta/llama-3.1-8b-instruct") == "llama 3.1 8b instruct"
    assert display_name_from_runtime("nvidia/nemotron-3-nano") == "nemotron 3 nano"
    assert is_embedding_model_name("bge-m3:latest") is True
    assert is_embedding_model_name("nomic-embed-text") is True
    assert is_embedding_model_name("mxbai-embed-large:335m") is True
    assert is_embedding_model_name("qwen3:8b") is False
    assert is_embedding_model_name("gemma4:31b-cloud") is False
    assert is_embedding_model_name("") is False
    assert embedding_model_rank("bge-m3:latest") < embedding_model_rank("nomic-embed-text")
    assert embedding_model_rank("nomic-embed-text") < embedding_model_rank("weird-vec")
    print("ollama_client self-check ok")
