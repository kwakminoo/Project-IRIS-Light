"""Hermes Agent API Server 클라이언트 — OpenAI 호환 채팅·모델 동기화."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
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


def is_iris_api_runtime_model(model: str) -> bool:
    """Iris 커스텀 API runtime id (`api:{provider_id}:{model}`) 여부."""
    return (model or "").strip().lower().startswith("api:")


def is_hermes_syncable_model(model: str) -> bool:
    """Hermes config.yaml default에 그대로 쓸 수 있는 모델명인지.

    Iris API runtime id(`api:…`)는 default에 넣으면 안 된다 — 반드시
    resolve_hermes_inference()로 푼 뒤 custom endpoint로 동기화한다.
    """
    name = (model or "").strip()
    if not name or is_iris_api_runtime_model(name):
        return False
    return True


@dataclass(frozen=True)
class HermesInferenceTarget:
    """Iris 피커 선택 → Hermes main-slot에 넣을 값."""

    model: str
    provider: str
    base_url: str = ""
    api_key: str = ""
    display: str = ""

    @property
    def label(self) -> str:
        return (self.display or self.model or "").strip()


def resolve_hermes_inference(
    runtime: str,
    *,
    db: Any = None,
    ollama_base_url: str = "http://127.0.0.1:11434/v1",
) -> HermesInferenceTarget:
    """Iris runtime 모델 id → Hermes custom/OpenAI-compat 타깃.

    - `api:{provider_id}:{model}` → 등록된 API의 base_url/api_key + 실제 모델명
    - Ollama/로컬 이름 → custom + :11434 (Hermes 0.19+ 권장)
    """
    raw = (runtime or "").strip()
    if not raw:
        raise ValueError("model required")

    from iris.storage.api_providers import get_api_provider, parse_runtime_model_id

    parsed = parse_runtime_model_id(raw)
    if parsed is not None:
        pid, api_model = parsed
        provider = get_api_provider(db, pid) if db is not None else None
        if provider is None or not (provider.base_url or "").strip():
            raise ValueError(
                "선택한 API가 없거나 Base URL이 없습니다. 설정 → API를 확인하세요."
            )
        base = (provider.base_url or "").strip().rstrip("/")
        return HermesInferenceTarget(
            model=api_model,
            provider="custom",
            base_url=base,
            api_key=(provider.api_key or "").strip(),
            display=f"{provider.name}/{api_model}",
        )

    ollama = (ollama_base_url or "http://127.0.0.1:11434/v1").strip().rstrip("/")
    if not ollama.endswith("/v1"):
        ollama = ollama + "/v1"
    return HermesInferenceTarget(
        model=raw,
        provider="custom",
        base_url=ollama,
        api_key="",
        display=raw,
    )


def infer_hermes_provider(model: str) -> str:
    """Iris 모델명 → Hermes provider.

    Iris 권장 스택은 로컬 Ollama(:11434)다. 클라우드 모델(`*:cloud`)도
    Ollama가 프록시하므로 `ollama-cloud`(직접 ollama.com + OLLAMA_API_KEY)가
    아니라 `ollama`로 둔다. `ollama-cloud`는 키 없으면 SSE finish_reason=error
    + 빈 content가 되어 Iris에 '(빈 응답)'만 보인다.
    """
    name = (model or "").strip().lower()
    if not name or is_iris_api_runtime_model(name):
        return "auto"
    # OpenRouter 스타일 vendor/model — Iris API runtime의 nvidia/... 는 위에서 차단
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
        """/health + /v1/models — 채팅과 동일한 Bearer 인증까지 확인."""
        if not self._health_ping_ok():
            return False
        if not self.api_key:
            return False
        try:
            self._get_json(f"{self.base_url}/models")
            return True
        except Exception:
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

    def set_inference_model(
        self,
        model: str,
        *,
        provider: str = "",
        base_url: str = "",
        api_key: str = "",
        target: HermesInferenceTarget | None = None,
    ) -> None:
        """Iris에서 고른 모델을 Hermes 런타임 기본 모델로 동기화.

        Iris API runtime id는 그대로 넣지 말고 ``resolve_hermes_inference`` /
        ``target=`` 로 푼 값(model/base_url/api_key)을 넘긴다.
        """
        if target is not None:
            model = target.model
            provider = target.provider
            base_url = target.base_url
            api_key = target.api_key
        model = (model or "").strip()
        if not model:
            return
        if is_iris_api_runtime_model(model):
            # 호출자가 runtime id를 그대로 넘긴 경우 — 오염 방지
            return
        provider = (provider or "").strip() or infer_hermes_provider(model)
        if provider == "auto":
            return
        # Hermes 0.19+: 로컬 OpenAI-compat는 custom + base_url
        if provider == "ollama":
            provider = "custom"
            if not (base_url or "").strip():
                base_url = "http://127.0.0.1:11434/v1"
        errors: list[str] = []
        if self._set_model_via_api(
            model, provider, errors, base_url=base_url, api_key=api_key
        ):
            return
        if self._set_model_via_cli(
            model, provider, errors, base_url=base_url, api_key=api_key
        ):
            return
        if errors:
            raise RuntimeError(errors[-1])

    def _set_model_via_api(
        self,
        model: str,
        provider: str,
        errors: list[str],
        *,
        base_url: str = "",
        api_key: str = "",
    ) -> bool:
        # Hermes(0.19+)엔 'ollama' provider가 없다 — 로컬 OpenAI-compat 프록시는
        # 'custom'으로 등록해야 한다 (base_url은 아래에서 그대로 127.0.0.1:11434).
        hermes_provider = "custom" if provider == "ollama" else provider
        body: dict[str, Any] = {
            "scope": "main",
            "provider": hermes_provider,
            "model": model,
            "confirm_expensive_model": True,
        }
        if (base_url or "").strip():
            body["base_url"] = base_url.strip()
        if api_key:
            body["api_key"] = api_key
        payload = json.dumps(body).encode("utf-8")
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
                        raw = resp.read().decode("utf-8", errors="replace")
                        try:
                            data = json.loads(raw) if raw else {}
                        except json.JSONDecodeError:
                            data = {}
                        # 비싼 모델 confirm 요구 — 이미 confirm=true 이므로 실패로 본다
                        if isinstance(data, dict) and data.get("confirm_required"):
                            errors.append(
                                str(data.get("confirm_message") or "model confirm required")
                            )
                            return False
                        if isinstance(data, dict) and data.get("ok") is False:
                            errors.append(str(data.get("detail") or data)[:200])
                            return False
                        return True
            except HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:200]
                errors.append(f"Hermes model API {e.code}: {detail or e.reason}")
            except (URLError, TimeoutError, OSError) as e:
                errors.append(f"Hermes model API 연결 실패: {e}")
        return False

    def _set_model_via_cli(
        self,
        model: str,
        provider: str,
        errors: list[str],
        *,
        base_url: str = "",
        api_key: str = "",
    ) -> bool:
        from iris.system.hermes_gateway import hermes_executable

        exe = hermes_executable(self.command)
        if not exe:
            errors.append(f"Hermes CLI 실행 파일을 찾을 수 없습니다: {self.command}")
            return False
        # Hermes(0.19+)엔 'ollama' provider가 없다 — 로컬 OpenAI-compat 프록시는
        # 'custom'으로 등록해야 한다 (base_url은 아래에서 그대로 127.0.0.1:11434).
        hermes_provider = "custom" if provider == "ollama" else provider
        cmds = [
            [exe, "config", "set", "model.provider", hermes_provider],
            [exe, "config", "set", "model.default", model],
        ]
        if (base_url or "").strip():
            cmds.append(
                [exe, "config", "set", "model.base_url", base_url.strip()]
            )
        elif provider in {"ollama", "custom"}:
            cmds.append(
                [
                    exe,
                    "config",
                    "set",
                    "model.base_url",
                    "http://127.0.0.1:11434/v1",
                ]
            )
        # api_key는 프로세스 목록에 노출되므로 CLI 대신 yaml 직접 기록
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
            if api_key:
                self._write_model_api_key(api_key, errors)
            return True
        except (OSError, subprocess.TimeoutExpired) as e:
            errors.append(f"Hermes CLI 실행 실패: {e}")
            return False

    def _write_model_api_key(self, api_key: str, errors: list[str]) -> None:
        """config.yaml model.api_key만 upsert (CLI argv 노출 회피)."""
        try:
            from iris.system.hermes_gateway import hermes_home

            path = hermes_home() / "config.yaml"
            if not path.is_file():
                return
            import yaml  # type: ignore

            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                return
            model = data.get("model")
            if not isinstance(model, dict):
                model = {}
            model["api_key"] = api_key
            data["model"] = model
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Hermes api_key 기록 실패: {exc}")

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
        headers = {**self._headers(json_body=True)}
        # urllib HTTP 헤더는 latin-1 — 한글 상태문구/모델라벨이 오면 요청 자체가 터진다
        try:
            (model or "").encode("latin-1")
            headers["X-Hermes-Model"] = model
        except UnicodeEncodeError:
            pass
        req = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
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
                hint = (
                    "Hermes API 키가 맞지 않습니다. "
                    "설정 → Hermes API Key가 "
                    r"%LOCALAPPDATA%\hermes\.env 의 API_SERVER_KEY 와 같아야 합니다."
                )
                raise RuntimeError(f"Hermes HTTP 401: {detail or hint}") from e
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
    assert infer_hermes_provider("api:41025a6367b9:nvidia/nemotron-3") == "auto"
    assert not is_hermes_syncable_model("api:x:nvidia/y")
    assert is_hermes_syncable_model("gemma4:26b")
    local = resolve_hermes_inference("gemma4:26b")
    assert local.provider == "custom" and "11434" in local.base_url
    assert local.model == "gemma4:26b"
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
    print("hermes_client self-check ok")
