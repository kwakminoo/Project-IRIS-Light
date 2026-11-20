"""PyQt6 HUD.

Agent-readable:
- Owns: 창, 채팅, 워크스페이스, 설정, Control 바인딩.
- Does not: Ollama/Iris Agent HTTP (인프라에 위임).
- Talks to: `UserTurnDispatcher`, Control Surface, `iris/storage`.
- Extend via: `chat` · `window` · `workspaces` · `control_actions`. 툴킷 교체는 `docs/guides/ui-toolkit-migration.md`.
"""

__all__ = ["MainWindow"]
