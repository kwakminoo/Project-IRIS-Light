"""Hermes Agent API Server 클라이언트 — OpenAI 호환 채팅·모델 동기화."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def api_root_from_base(base_url: str) -> str:
    """http://127.0.0.1:8642/v1 → http://127.0.0.1:8642"""
    raw = (base_url or "").strip().rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw or "http://127.0.0.1:8642"


def infer_hermes_provider(model: str) -> str:
    """Iris Ollama 모델명 → Hermes provider 힌트."""
    name = (model or "").strip().lower()
    if not name:
        return "auto"
    if "/" in name:
        return "openrouter"
    if name.endswith("-cloud") or name.endswith(":cloud") or "ollama" in name:
        return "ollama-cloud"
    return "ollama-cloud"


class HermesClient:
    """Hermes gateway API Server HTTP 어댑터."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8642/v1",
        *,
        api_key: str = "",
        command: str = "hermes",
        timeout_sec: float = 300.0,
    ) -> None:
        self.base_url = (base_url or "http://127.0.0.1:8642/v1").strip().rstrip("/")
        self.api_root = api_root_from_base(self.base_url)
        self.api_key = (api_key or "").strip()
        self.command = (command or "hermes").strip() or "hermes"
        self.timeout_sec = timeout_sec

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health_ok(self) -> bool:
        for path in (f"{self.api_root}/health", f"{self.base_url}/health"):
            try:
                req = Request(path, method="GET", headers=self._headers())
                with urlopen(req, timeout=5.0) as resp:
                    if resp.status != 200:
                        continue
                    body = json.loads(resp.read().decode("utf-8"))
                    if isinstance(body, dict) and str(body.get("status", "")).lower() == "ok":
                        return True
            except Exception:
                continue
        return False

    def list_models(self) -> list[str]:
        try:
            data = self._get_json(f"{self.base_url}/models")
        except Exception:
            return ["hermes-agent"]
        out: list[str] = []
        for item in data.get("data") or []:
            if isinstance(item, dict):
                mid = str(item.get("id") or "").strip()
                if mid:
                    out.append(mid)
        return out or ["hermes-agent"]

    def resolve_request_model(self, iris_model: str) -> str:
        """API 요청 model 필드 — 서버가 광고하는 이름 우선."""
        advertised = self.list_models()
        if len(advertised) == 1:
            return advertised[0]
        if iris_model in advertised:
            return iris_model
        return advertised[0]

    def set_inference_model(self, model: str) -> None:
        """Iris에서 고른 모델을 Hermes 런타임 기본 모델로 동기화."""
        model = (model or "").strip()
        if not model:
            return
        provider = infer_hermes_provider(model)
        errors: list[str] = []
        if self._set_model_via_api(model, provider, errors):
            return
        if self._set_model_via_cli(model, provider, errors):
            return
        if errors:
            raise RuntimeError(errors[-1])

    def _set_model_via_api(self, model: str, provider: str, errors: list[str]) -> bool:
        payload = json.dumps(
            {"scope": "main", "provider": provider, "model": model}
        ).encode("utf-8")
        for path in (f"{self.api_root}/api/model/set", f"{self.api_root}/api/model/set/"):
            try:
                req = Request(
                    path,
                    data=payload,
                    headers=self._headers(json_body=True),
                    method="POST",
                )
                with urlopen(req, timeout=15.0) as resp:
                    if 200 <= resp.status < 300:
                        return True
            except HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:200]
                errors.append(f"Hermes model API {e.code}: {detail or e.reason}")
            except (URLError, TimeoutError, OSError) as e:
                errors.append(f"Hermes model API 연결 실패: {e}")
        return False

    def _set_model_via_cli(self, model: str, provider: str, errors: list[str]) -> bool:
        cmds = [
            [self.command, "config", "set", "model.provider", provider],
            [self.command, "config", "set", "model.default", model],
        ]
        try:
            for cmd in cmds:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "").strip()
                    errors.append(
                        f"Hermes CLI 실패 ({' '.join(cmd)}): {err or proc.returncode}"
                    )
                    return False
            return True
        except (OSError, subprocess.TimeoutExpired) as e:
            errors.append(f"Hermes CLI 실행 실패: {e}")
            return False

    def stream_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> Iterator[dict[str, Any]]:
        """
        /v1/chat/completions SSE.
        yield: {"content": str|None, "tool_progress": str|None, "done": bool}
        """
        request_model = self.resolve_request_model(model)
        payload = {
            "model": request_model,
            "messages": messages,
            "stream": True,
        }
        req = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                **self._headers(json_body=True),
                "X-Hermes-Model": model,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                event_name = ""
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line:
                        event_name = ""
                        continue
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        yield {"content": None, "tool_progress": None, "done": True}
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event_name == "hermes.tool.progress":
                        msg = _format_tool_progress(obj)
                        if msg:
                            yield {"content": None, "tool_progress": msg, "done": False}
                        continue
                    for choice in obj.get("choices") or []:
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta") or {}
                        if not isinstance(delta, dict):
                            continue
                        chunk = delta.get("content")
                        if isinstance(chunk, str) and chunk:
                            yield {"content": chunk, "tool_progress": None, "done": False}
                    if obj.get("type") == "hermes.tool.progress":
                        msg = _format_tool_progress(obj)
                        if msg:
                            yield {"content": None, "tool_progress": msg, "done": False}
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Hermes HTTP {e.code}: {detail or e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Hermes 연결 실패: {e.reason}") from e

    def _get_json(self, url: str) -> dict[str, Any]:
        req = Request(url, method="GET", headers=self._headers())
        with urlopen(req, timeout=min(15.0, self.timeout_sec)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else {}


def host_label_for_hermes(base_url: str) -> str:
    try:
        netloc = urlparse(api_root_from_base(base_url)).netloc
        return netloc or "localhost"
    except Exception:
        return "localhost"


def _format_tool_progress(obj: dict[str, Any]) -> str:
    if not isinstance(obj, dict):
        return ""
    for key in ("message", "status", "tool", "name", "detail"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "tool running"
