"""메인 윈도우/윈도우 크롬 (main_window, top_status_header, frameless_chrome, startup_intro, cyberspace_background).

Agent-readable:
- Owns: MainWindow, 프레임 없는 크롬, 시작 인트로.
- Does not: Iris Agent/Ollama HTTP 구현, 스킬 마크다운.
- Talks to: `UserTurnDispatcher`, Control Surface, 워크스페이스 페이지.
- Extend via: 셸 동작은 여기. 새 에이전트 도구는 스킬. 모델 클라이언트는 `iris/infrastructure`.
"""
