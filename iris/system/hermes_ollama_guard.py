"""Hermes custom 프로파일의 Ollama 전용 ``options.num_ctx`` 가드.

설치본 ``plugins/model-providers/custom/__init__.py`` 한 분기만 고친다.
패턴이 없으면 파일을 덮어쓰지 않는다. 채팅 쪽 ``ollama_num_ctx`` 정리는 별도로 계속된다.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_IF_OLLAMA_CTX = re.compile(r"^([ \t]*)if ollama_num_ctx:\s*$")
_OPTIONS_ASSIGN = re.compile(r"""\[\s*['"]options['"]\s*\]\s*=""")


def looks_like_ollama_endpoint(base_url: str | None) -> bool:
    """Hermes ``_looks_like_ollama_endpoint`` 와 같은 규칙.

    포트 11434, 또는 호스트가 ollama / ``*.ollama.com`` / 라벨에 ollama.
    빈 문자열·깨진 포트는 False.
    """
    raw = (base_url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    try:
        if parsed.port == 11434:
            return True
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return bool(host) and (
        host == "ollama.com" or host.endswith(".ollama.com") or "ollama" in host.split(".")
    )


def _custom_provider_path(agent_root: Path) -> Path:
    return Path(agent_root) / "plugins" / "model-providers" / "custom" / "__init__.py"


def ollama_options_guard_present(agent_root: Path) -> bool:
    """기준선에 Ollama URL 가드가 이미 있으면 True. 디스크를 쓰지 않는다."""
    path = _custom_provider_path(agent_root)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if (
            stripped.startswith("if ")
            and "ollama_num_ctx" in stripped
            and "_looks_like_ollama_endpoint" in stripped
        ):
            return True
    return False


def apply_ollama_options_guard(agent_root: Path) -> bool:
    """``options`` 주입을 Ollama URL 로만 제한.

    **install/update baseline 전용.** gateway 기동에서는 호출하지 않는다.
    True 는 이번에 파일 내용이 바뀐 경우만. 이미 가드가 있거나 패턴이 없으면 False.
    패턴이 없으면 원문을 유지하고 경고만 남긴다.
    """
    path = _custom_provider_path(agent_root)
    if not path.is_file():
        log.warning("ollama options guard: custom provider file missing")
        return False
    if ollama_options_guard_present(agent_root):
        return False
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    target: int | None = None
    for i, line in enumerate(lines):
        if _IF_OLLAMA_CTX.match(line.rstrip("\r\n")) is None:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and _OPTIONS_ASSIGN.search(lines[j]):
            target = i
            break
    if target is None:
        log.warning("ollama options guard: if ollama_num_ctx options pattern not found")
        return False
    indent_m = _IF_OLLAMA_CTX.match(lines[target].rstrip("\r\n"))
    indent = indent_m.group(1) if indent_m else ""
    nl = "\r\n" if lines[target].endswith("\r\n") else "\n"
    lines[target] = (
        f"{indent}# iris: ollama-options-guard{nl}"
        f'{indent}if ollama_num_ctx and _looks_like_ollama_endpoint(ctx.get("base_url")):{nl}'
    )
    new = "".join(lines)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8", newline="")
    return True


def sync_model_ollama_num_ctx(base_url: str) -> None:
    """활성 custom base_url 에 맞춰 config.yaml ``model.ollama_num_ctx`` 를 맞춘다.

    비-Ollama 는 키 삭제. Ollama 는 없거나 64K 미만이면 64000, 더 크면 유지.
    API 키는 인자로 받지 않는다.
    """
    from iris.infrastructure.hermes_credentials import hermes_home
    from iris.system.setup_protocol import HERMES_MIN_OLLAMA_NUM_CTX

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
        data["model"] = model
    if looks_like_ollama_endpoint(base_url):
        try:
            cur = int(model.get("ollama_num_ctx") or 0)
        except (TypeError, ValueError):
            cur = 0
        if cur >= HERMES_MIN_OLLAMA_NUM_CTX:
            return
        model["ollama_num_ctx"] = HERMES_MIN_OLLAMA_NUM_CTX
    else:
        if "ollama_num_ctx" not in model:
            return
        model.pop("ollama_num_ctx", None)
    data["model"] = model
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def note_after_provider_direct_ok(
    provider: Any,
    *,
    db: Any,
    hermes_enabled: bool,
    hermes_base_url: str,
) -> str:
    """직접 연결 성공 뒤에 붙일 한 줄. 게이트웨이를 새로 띄우지 않는다."""
    if not hermes_enabled:
        return ""
    from iris.system.hermes_gateway import probe_gateway_health

    if not probe_gateway_health(hermes_base_url, timeout_sec=1.5).ok:
        return "채팅 경로 미확인"
    models = list(getattr(provider, "models", None) or [])
    model = str(models[0] if models else "").strip()
    if not model:
        return "채팅 경로 미확인"
    secret = str(getattr(provider, "api_key", "") or "").strip()
    try:
        from iris.infrastructure.hermes_client import HermesClient, resolve_hermes_inference
        from iris.storage.api_providers import runtime_model_id

        target = resolve_hermes_inference(runtime_model_id(str(provider.id), model), db=db)
        client = HermesClient(hermes_base_url, timeout_sec=20.0)
        client.set_inference_model(target.model, target=target)
        for ev in client.stream_chat(target.model, [{"role": "user", "content": "ping"}]):
            if ev.get("content"):
                return "Hermes 채팅 경로 응답 있음"
            if ev.get("done"):
                break
        return "Hermes 채팅 응답 없음"
    except Exception as exc:  # noqa: BLE001
        text = _redact(_error_blob(exc), secret)
        if _is_options_400(text):
            return f"Hermes 채팅 실패 (options): {text[:160]}"
        return f"Hermes 채팅 실패: {text[:160]}"


def _error_blob(exc: BaseException) -> str:
    from urllib.error import HTTPError

    if isinstance(exc, HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        return f"HTTP {exc.code} {body}"
    return str(exc)


def _redact(text: str, secret: str) -> str:
    out = (text or "").replace("\n", " ").strip()
    if secret:
        out = out.replace(secret, "•••")
    return out


def _is_options_400(text: str) -> bool:
    low = (text or "").lower()
    if "options" not in low:
        return False
    return "400" in low or "unknown name" in low or "unsupported" in low
