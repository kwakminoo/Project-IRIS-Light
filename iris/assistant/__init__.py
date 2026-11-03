"""Assistant 패키지 — Light에서는 상태 표시 스텁만.

Agent-readable:
- Owns: Iris Agent 헬스 한 줄 (`external_backend_status_line`).
- Does not: 에이전트 실행. OpenClaw는 미사용.
- Talks to: `iris.config.settings`, UI 상태 칩.
- Extend via: 문구만 여기. 새 백엔드는 `iris/infrastructure` 클라이언트.
"""
