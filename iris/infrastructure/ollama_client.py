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

    def __post_init__(self) -> None:
        if not self.catalog_name:
            object.__setattr__(self, "catalog_name", display_name_from_runtime(self.name))

    @property
    def is_cloud(self) -> bool:
        n = self.name.lower()
        return n.endswith("-cloud") or ":cloud" in n or n.endswith(":cloud")


def display_name_from_runtime(runtime_name: str) -> str:
    """gemma4:31b-cloud → gemma4:31b"""
    n = runtime_name.strip()
    if n.endswith("-cloud"):
        return n[: -len("-cloud")]
    if n.endswith(":cloud"):
        return n[: -len(":cloud")]
    return n


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
        self, *, probe: bool = True, tools_only: bool = True, max_workers: int = 6
    ) -> list[OllamaModelInfo]:
        """
        무료 플랜에서 사용 가능한 클라우드 모델만 반환.
        tools_only=True면 도구 호출(tool-calling) 지원 모델만 남긴다.
        probe=False면 카탈로그 전체(Pro 포함) 반환.
        """
        catalog = self.list_cloud_catalog()
        if not probe or not catalog:
            return catalog

        def _ok(name: str) -> bool:
            if not self.probe_model_available(name):
                return False
            if tools_only and not self.model_supports_tools(name):
                return False
            return True

        available: list[OllamaModelInfo] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_ok, m.name): m for m in catalog}
            for fut in as_completed(futures):
                model = futures[fut]
                try:
                    if fut.result():
                        available.append(model)
                except Exception:
                    pass
        available.sort(key=lambda x: x.catalog_name.lower())
        return available if available else catalog

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


    def probe_model_available(self, runtime_name: str, *, timeout_sec: float = 25.0) -> bool:
        """구독 없이 호출 가능하면 True (무료 tier 포함)."""
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
            return True
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace").lower()
            if "subscription" in detail or "upgrade" in detail:
                return False
            if "not found" in detail:
                return False
            return False
        except (URLError, TimeoutError, json.JSONDecodeError, OSError):
            return False

    def _local_cloud_fallback(self) -> list[OllamaModelInfo]:
        models = self.list_models()
        cloud = [m for m in models if m.is_cloud]
        return cloud if cloud else models

    def list_cloud_preferring(self) -> list[OllamaModelInfo]:
        """하위 호환 — 무료 클라우드 모델 우선."""
        return self.list_free_cloud_models(probe=True)

    def list_chat_models(self, *, probe_cloud: bool = True) -> list[OllamaModelInfo]:
        """로컬 설치 모델 + 무료 클라우드 병합 (로컬 우선). Hermes/Ollama 공용."""
        local = self.list_models()
        cloud = self.list_free_cloud_models(probe=probe_cloud)
        seen: set[str] = set()
        out: list[OllamaModelInfo] = []
        for m in [*local, *cloud]:
            if m.name in seen:
                continue
            seen.add(m.name)
            out.append(m)
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
        호출 측에서 결과가 쓸모없을 수 있음을 감안해야 한다."""
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
    # 도구 지원 필터 핵심 로직 자체 점검(네트워크 불필요).
    assert supports_tools_capability(["completion", "tools", "thinking"]) is True
    assert supports_tools_capability(["completion", "vision"]) is False
    assert supports_tools_capability([]) is False
    assert supports_tools_capability(None) is False
    print("ollama_client self-check ok")
