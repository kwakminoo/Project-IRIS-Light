"""IRIS Light 설정 — Ollama / Hermes 연결 중심."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """Light 버전 런타임 설정."""

    # Ollama (OpenAI 호환 엔드포인트)
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_model: str = ""

    # Hermes Agent
    hermes_enabled: bool = True
    hermes_command: str = "hermes"
    hermes_base_url: str = "http://127.0.0.1:8642/v1"
    hermes_api_key: str = ""

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
    return Settings(
        ollama_base_url=os.environ.get("IRIS_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").strip(),
        ollama_model=model,
        hermes_enabled=os.environ.get("IRIS_HERMES_ENABLED", "1").strip() not in ("0", "false", "False"),
        hermes_command=os.environ.get("IRIS_HERMES_COMMAND", "hermes").strip() or "hermes",
        hermes_base_url=os.environ.get("IRIS_HERMES_BASE_URL", "http://127.0.0.1:8642/v1").strip()
        or "http://127.0.0.1:8642/v1",
        hermes_api_key=os.environ.get("IRIS_HERMES_API_KEY", "").strip(),
        data_go_kr_service_key=os.environ.get("IRIS_DATA_GO_KR_SERVICE_KEY", "").strip(),
        model_name=model or "(unset)",
        model_names=(model,) if model else (),
    )
