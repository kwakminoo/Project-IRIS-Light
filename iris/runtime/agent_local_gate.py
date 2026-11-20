"""에이전트가 켜져 있으면 채팅 의도 가로채기를 모델 도구에 넘긴다."""

from __future__ import annotations


def agent_owns_local_intents(agent_enabled: bool) -> bool:
    """True면 IDE·화면·위키·PDF·확장 설치·사진 코드의 신규 가로채기를 하지 않는다."""
    return bool(agent_enabled)
