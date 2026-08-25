"""Hermes Agent API Server 클라이언트 — OpenAI 호환 채팅·모델 동기화."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from iris.infrastructure.hermes_credentials import resolve_hermes_api_key


def api_root_from_base(base_url: str) -> str:
    """http://127.0.0.1:8642/v1 → http://127.0.0.1:8642"""
    raw = (base_url or "").strip().rstrip("/")
    if raw.endswith("/v1"):
        raw = raw[:-3]
    return raw or "http://127.0.0.1:8642"


def infer_hermes_provider(model: str) -> str:
    """Iris 모델명 → Hermes provider.

    Iris 권장 스택은 로컬 Ollama(:11434)다. 클라우드 모델(`*:cloud`)도
    Ollama가 프록시하므로 `ollama-cloud`(직접 ollama.com + OLLAMA_API_KEY)가
    아니라 `ollama`로 둔다. `ollama-cloud`는 키 없으면 SSE finish_reason=error
    + 빈 content가 되어 Iris에 '(빈 응답)'만 보인다.
    """
    name = (model or "").strip().lower()
    if not name:
        return "auto"
    if "/" in name:
        return "openrouter"
    return "ollama"


def _sse_error_message(obj: dict[str, Any]) -> str:
    """SSE chunk의 error / finish_reason=error 메시지 추출."""
    err = obj.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("code") or ""
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    if isinstance(err, str) and err.strip():
        return err.strip()
    for choice in obj.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        if str(choice.get("finish_reason") or "").lower() != "error":
            continue
        return "Hermes stream finished with error"
    return ""


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
        self.api_key = resolve_hermes_api_key(api_key)
        self.command = (command or "hermes").strip() or "hermes"
        self.timeout_sec = timeout_sec

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _health_ping_ok(self) -> bool:
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

    def health_ok(self) -> bool:
        """/health — 프로세스 생존만 (Bearer 불필요)."""
        return self._health_ping_ok()

    def gateway_ready(self) -> bool:
        """/health + /v1/models — 프로세스·키 존재. 채팅 401은 probe_chat_auth()."""
        if not self._health_ping_ok():
            return False
        if not self.api_key:
            return False
        try:
            self._get_json(f"{self.base_url}/models")
            return True
        except Exception:
            return False

    def probe_chat_auth(self) -> str:
        """채팅과 같은 POST /v1/chat/completions 로 Bearer를 검사.

        GET /v1/models 는 키가 틀리거나 없어도 200인 경우가 있어
        검사·Connected는 통과하고 보내기만 401이 난다.
        메시지 필드를 빼면 인증 통과 시 보통 400/422로 바로 끝나고,
        실패 시 401로 끝나도록(추론 호출 최소화) 만든다.

        Returns: 'ok' | 'unauthorized' | 'unreachable'
        """
        if not self.api_key:
            return "unauthorized"
        payload = json.dumps(
            {
                "model": "hermes-agent",
                "stream": False,
                "max_tokens": 1,
            }
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers=self._headers(json_body=True),
            method="POST",
        )
        try:
            with urlopen(req, timeout=3.0) as resp:
                resp.read(64)
            return "ok"
        except HTTPError as e:
            try:
                e.read()
            except Exception:
                pass
            if e.code == 401:
                return "unauthorized"
            return "ok"
        except (URLError, TimeoutError, OSError):
            return "unreachable"

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
        # 로컬 Ollama 프록시 — cloud 모델도 :11434 경유
        if provider == "ollama":
            cmds.append(
                [
                    self.command,
                    "config",
                    "set",
                    "model.base_url",
                    "http://127.0.0.1:11434/v1",
                ]
            )
        try:
            for cmd in cmds:
                from iris.system.win_subprocess import no_window_kwargs

                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                    **no_window_kwargs(),
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
                    err_msg = _sse_error_message(obj)
                    if err_msg:
                        raise RuntimeError(f"Hermes: {err_msg}")
                    if event_name == "hermes.tool.progress":
                        msg = _format_tool_progress(obj)
                        if msg:
                            yield {"content": None, "tool_progress": msg, "done": False}
                        continue
                    for choice in obj.get("choices") or []:
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta") or {}
                        if isinstance(delta, dict):
                            chunk = delta.get("content")
                            if isinstance(chunk, str) and chunk:
                                yield {
                                    "content": chunk,
                                    "tool_progress": None,
                                    "done": False,
                                }
                        # 일부 응답은 delta 대신 message.content만 옴
                        message = choice.get("message") or {}
                        if isinstance(message, dict):
                            full = message.get("content")
                            if isinstance(full, str) and full:
                                yield {
                                    "content": full,
                                    "tool_progress": None,
                                    "done": False,
                                }
                    if obj.get("type") == "hermes.tool.progress":
                        msg = _format_tool_progress(obj)
                        if msg:
                            yield {"content": None, "tool_progress": msg, "done": False}
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            if e.code == 401:
                raise RuntimeError(
                    "Hermes HTTP 401 Unauthorized. "
                    "시작 프로토콜 「다시 설정」으로 API 키를 맞추고, "
                    "로컬 최소 모델을 받거나 Ollama 클라우드 로그인을 확인하세요."
                ) from e
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


if __name__ == "__main__":
    assert infer_hermes_provider("gemma4:31b-cloud") == "ollama"
    assert infer_hermes_provider("gemma4:26b") == "ollama"
    assert infer_hermes_provider("anthropic/claude") == "openrouter"
    assert "OLLAMA_API_KEY" in _sse_error_message(
        {
            "choices": [{"finish_reason": "error", "delta": {}}],
            "error": {"message": "No usable credentials. Set OLLAMA_API_KEY."},
        }
    )
    assert _sse_error_message({"choices": [{"delta": {"content": "hi"}}]}) == ""
    resolved = resolve_hermes_api_key("")
    client = HermesClient("http://127.0.0.1:8642/v1", api_key="")
    assert client.api_key == resolved
    empty = HermesClient("http://127.0.0.1:1/v1", api_key="")
    if not empty.api_key:
        assert empty.probe_chat_auth() == "unauthorized"
    print("hermes_client self-check ok")
