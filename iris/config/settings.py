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

    # Iris Agent policy.
    agent_enabled: bool = True
    agent_command: str = "hermes"
    agent_base_url: str = "http://127.0.0.1:8642/v1"
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


def _env_bool(name: str, *, default: bool = True) -> bool:
    import os

    text = str(os.environ.get(name) or "").strip()
    return default if not text else text.lower() not in ("0", "false", "no", "off")


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
    raw_key = os.environ.get("IRIS_AGENT_API_KEY", "").strip()
    try:
        from iris.infrastructure.iris_agent_credentials import resolve_hermes_api_key

        agent_api_key = resolve_hermes_api_key(raw_key)
    except Exception:
        agent_api_key = raw_key
    raw_base = os.environ.get(
        "IRIS_AGENT_BASE_URL", "http://127.0.0.1:8642/v1"
    ).strip()
    try:
        from iris.infrastructure.iris_agent_client import normalize_iris_agent_openai_base_url

        agent_base = normalize_iris_agent_openai_base_url(raw_base)
    except Exception:
        agent_base = raw_base.strip() or "http://127.0.0.1:8642/v1"
    return Settings(
        ollama_base_url=os.environ.get("IRIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").strip(),
        ollama_model=model,
        agent_enabled=_env_bool("IRIS_AGENT_ENABLED", default=True),
        agent_command=os.environ.get("IRIS_AGENT_COMMAND", "hermes").strip() or "hermes",
        agent_base_url=agent_base,
        agent_api_key=agent_api_key,
        data_go_kr_service_key=os.environ.get("IRIS_DATA_GO_KR_SERVICE_KEY", "").strip(),
        model_name=model or "(unset)",
        model_names=(model,) if model else (),
    )
