"""사용자에게 보이는 채팅 기록의 정본 (Phase 4 / §10.1 gate 3).

| 기억 | 주인 | 용도 |
|---|---|---|
| Iris SQLite ``chat_messages`` | Iris 제품 | UI 히스토리·사이드바·재개 **정본** |
| 런타임 session DB | Iris Agent 런타임 | 루프 컨텍스트. UI 정본 아님 |
| MEMORY / USER | Iris Agent 런타임 | 페르소나·선호. 턴 로그 아님 |
| Iris 위키 / 메일 / 일정 | Iris 제품 | 노트·사실. 채팅 턴 아님 |

제품 화면이 읽는 유일한 채팅 저장소는 ``CHAT_PRODUCT_OF_RECORD`` 다.
"""

from __future__ import annotations

# Iris DB table name — ChatSession / conversations.append_message 경로.
CHAT_PRODUCT_OF_RECORD = "iris_sqlite_chat_messages"

# Hermes/agent session store — ephemeral for the agent loop only.
AGENT_SESSION_DB_ROLE = "runtime_ephemeral_not_ui"


def is_chat_product_of_record(store: str) -> bool:
    return (store or "").strip() == CHAT_PRODUCT_OF_RECORD
