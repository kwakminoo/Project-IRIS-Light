"""Hermes API 키·.env — gateway/client 공용 (순환 import 방지)."""

from __future__ import annotations

from pathlib import Path

from iris.infrastructure.agent_runtime import iris_agent_home

# 플레이스홀더·데모 키 잔존 → 채팅 401. token_urlsafe(32)는 보통 43자·마커 없음.
_WEAK_KEY_MARKERS = (
    "change-me",
    "changeme",
    "replace-me",
    "your-api-key",
    "todo",
    "placeholder",
    "test",
    "secret",
)


def hermes_home() -> Path:
    """제품 런타임 홈. ``iris_agent_home()`` 과 동일 (Phase 1 단일 함수)."""
    return iris_agent_home()


def is_weak_hermes_api_key(key: str) -> bool:
    """없거나 짧거나 플레이스홀더면 True. 강한 기존 키는 False(불필요 rotate 금지)."""
    s = (key or "").strip()
    if not s or len(s) < 24:
        return True
    low = s.lower()
    return any(m in low for m in _WEAK_KEY_MARKERS)


def load_hermes_dotenv() -> dict[str, str]:
    """런타임 홈 ``.env`` → dict (API_SERVER_* 등)."""
    path = hermes_home() / ".env"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        out[key] = val.strip().strip('"').strip("'")
    return out


def resolve_hermes_api_key(api_key: str = "") -> str:
    """게이트웨이가 실제로 검사하는 키를 고른다.

    /health 는 Bearer 없이 200이라 Connected로 보이지만,
    /v1/chat/completions 는 API_SERVER_KEY가 필요하다.
    Hermes .env 값이 있으면 그걸 쓰고, 없을 때만 Iris 설정/환경변수 키를 쓴다.
    """
    env_key = load_hermes_dotenv().get("API_SERVER_KEY", "").strip()
    if env_key:
        return env_key
    return (api_key or "").strip()


if __name__ == "__main__":
    assert is_weak_hermes_api_key("change-me-please")
    assert is_weak_hermes_api_key("short")
    assert not is_weak_hermes_api_key("x" * 32)
    assert resolve_hermes_api_key("") == load_hermes_dotenv().get("API_SERVER_KEY", "").strip()
    print("hermes_credentials self-check ok")
