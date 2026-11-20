"""IRIS Light 설정 — Ollama / Iris Agent 연결 중심."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """Light 버전 런타임 설정."""

    # Ollama (OpenAI 호환 엔드포인트)
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_model: str = ""

    # Iris Agent policy (canonical).
    # agent_base_url empty = product InternalSidecar (no HTTP gateway endpoint).
    # Opt-in external gateway: set IRIS_AGENT_BASE_URL explicitly.
    # (Rename any leftover IRIS_HERMES_* keys — product reads AGENT only.)
    agent_enabled: bool = True
    agent_command: str = "iris-agent"
    agent_base_url: str = ""
    agent_api_key: str = ""

    # 공공데이터포털 — 한국천문연구원 특일(공휴일) API
    data_go_kr_service_key: str = ""

    # UI
    always_listen_speech_rms: float = 0.02

    # 표시용 (상태 칩)
    model_name: str = ""
    model_names: tuple[str, ...] = field(default_factory=tuple)

    # 캡처 디스크 저장 여부 (모니터 썸네일은 메모리)
    store_screenshots: bool = False
    save_captures_to_disk: bool = False
    capture_dir: Path = field(default_factory=lambda: Path.home() / ".iris-light" / "captures")


def default_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _env_pick(*names: str, default: str = "") -> str:
    """First non-empty env among names. Product agent keys are ``IRIS_AGENT_*`` only."""
    import os

    for name in names:
        if name not in os.environ:
            continue
        text = str(os.environ.get(name) or "").strip()
        if text:
            return text
    return default


def _env_bool_pick(*names: str, default: bool = True) -> bool:
    """First present non-empty env among names as bool; else default."""
    import os

    for name in names:
        if name not in os.environ:
            continue
        text = str(os.environ.get(name) or "").strip()
        if not text:
            continue
        return text not in ("0", "false", "False", "no", "off", "NO", "OFF")
    return default


_LEGACY_LOCAL_GATEWAY_PORT = 8642  # historical Hermes api_server default


def _is_legacy_local_gateway_url(url: str) -> bool:
    """Legacy Hermes loopback HTTP gateway (historical default port)."""
    from urllib.parse import urlparse

    text = (url or "").strip()
    if not text:
        return False
    try:
        parsed = urlparse(text if "://" in text else f"http://{text}")
        host = (parsed.hostname or "").lower()
        port = parsed.port
        if port is None:
            # urlparse may omit port when scheme is missing; recover from ":port/"
            for part in text.split("/"):
                if ":" in part and not part.endswith(":"):
                    maybe = part.rsplit(":", 1)[-1]
                    if maybe.isdigit():
                        port = int(maybe)
                        break
        return host in ("127.0.0.1", "localhost", "::1") and port == _LEGACY_LOCAL_GATEWAY_PORT
    except (ValueError, TypeError):
        return False


def _product_agent_base_url_from_env() -> str:
    """Non-empty ``IRIS_AGENT_BASE_URL``; any ``:8642`` value is ignored (sidecar-only).

    Does not rewrite user env files. Non-8642 URLs stay opt-in external gateway.
    ``IRIS_HERMES_BASE_URL`` is not read — rename to AGENT if needed.
    """
    import os

    if "IRIS_AGENT_BASE_URL" not in os.environ:
        return ""
    text = str(os.environ.get("IRIS_AGENT_BASE_URL") or "").strip()
    if not text:
        return ""
    # Force strip — historical Hermes api_server port is never a live product URL.
    if f":{_LEGACY_LOCAL_GATEWAY_PORT}" in text or _is_legacy_local_gateway_url(text):
        return ""
    return text


def load_settings(env_path: Path | None = None) -> Settings:
    """환경변수/.env에서 최소 설정 로드."""
    import os

    path = env_path or default_env_path()
    if path.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(path)
        except ImportError:
            pass

    model = os.environ.get("IRIS_OLLAMA_MODEL", "").strip()
    raw_key = _env_pick("IRIS_AGENT_API_KEY", default="")
    try:
        from iris.infrastructure.iris_agent_credentials import resolve_agent_api_key

        agent_api_key = resolve_agent_api_key(raw_key)
    except Exception:
        agent_api_key = raw_key
    raw_base = _product_agent_base_url_from_env()
    try:
        from iris.infrastructure.iris_agent_client import normalize_iris_agent_openai_base_url

        agent_base = normalize_iris_agent_openai_base_url(raw_base)
    except Exception:
        agent_base = raw_base.strip()
    return Settings(
        ollama_base_url=os.environ.get("IRIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").strip(),
        ollama_model=model,
        agent_enabled=_env_bool_pick("IRIS_AGENT_ENABLED", default=True),
        agent_command=_env_pick("IRIS_AGENT_COMMAND", default="iris-agent")
        or "iris-agent",
        agent_base_url=agent_base,
        agent_api_key=agent_api_key,
        data_go_kr_service_key=os.environ.get("IRIS_DATA_GO_KR_SERVICE_KEY", "").strip(),
        model_name=model or "(unset)",
        model_names=(model,) if model else (),
    )
