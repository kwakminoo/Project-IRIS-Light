"""외부 런타임 HTTP 어댑터.

Agent-readable:
- Owns: Ollama·OpenAI-compat·메일·캘린더·검색 클라이언트 + opt-in agent HTTP client.
- Does not: 프롬프트 오케스트레이션, PyQt 위젯.
- Talks to: Ollama `:11434`, 외부 API. Product chat is InternalSidecar (not HTTP gateway).
- Extend via: 새 제공자는 `*_client.py` 하나. 도구 추가는 Iris Agent 스킬이 우선.
"""
