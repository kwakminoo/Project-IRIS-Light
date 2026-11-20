"""창 목록·IDE 입력 등 UI 지원 자동화.

Agent-readable:
- Owns: 창 제어(`window_controller`), IDE 입력(`ide_input`).
- Does not: 채팅 턴, Iris Agent 도구 실행.
- Talks to: Win32, UI.
- Extend via: 이 패키지. 화면 학습 녹화는 `iris/learning`.
"""
