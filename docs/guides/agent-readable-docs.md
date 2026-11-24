# Agent-readable 문서 · 주석 계약

| 항목 | 내용 |
|------|------|
| 목적 | 인간 + AI 코딩 에이전트가 **같은 맥락**을 읽게 한다 (피드백 No.6) |
| 작성일 | 2026-09-23 |

---

## 1. 규칙 (1페이지)

패키지/`__init__.py` 또는 모듈 상단에 아래 블록을 둔다 (한국어·영어 혼용 OK, **키는 고정**).

```text
"""한 줄 역할.

Agent-readable:
- Owns: <이 모듈이 소유하는 경계>
- Does not: <절대 하지 않는 일 / 위임 대상>
- Talks to: <호출·피호출 경로>
- Extend via: <확장 시 손댈 곳 — 보통 integrations/ 또는 본 패키지>
"""
```

| 키 | 의미 |
|----|------|
| Owns | 바운디드 컨텍스트 한 줄 |
| Does not | 오케스트레이터·추론·도구 재구현 금지 등 |
| Talks to | Gateway 포트, MCP, UI 시그널 |
| Extend via | 기여자 진입점 |

도메인 전체 지도는 계속 [`docs/domain.md`](../domain.md) · [`docs/ia/IA.md`](../ia/IA.md)가 정본.

---

## 2. 개선 전후 예시

### 예시 A — `iris/mcp/__init__.py`

**Before**

```python
"""Iris MCP adapters (stdio bridges for Iris Agent)."""
```

**After** — 저장소 반영본 참고.

### 예시 B — `iris/runtime/__init__.py`

**Before**

```python
"""Runtime helpers for conversation turn dispatch."""
```

**After** — 저장소 반영본 참고.

발표·심사 시 이 문서 + git blame/diff로 “개선했다”를 인용한다.

---

## 3. 문서 계층

| 층 | 산출물 | 독자 |
|----|--------|------|
| 도메인 | `domain.md`, `IA.md`, `IRIS_개발문서.md` | 인간·에이전트 |
| 확장·수정 위치 | `guides/extending-iris.md` §3–§4 | 기여자 |
| 검증 | `검증/*`, `_check_*.py` | 검증관·CI |
| 패키지 pydoc | 모든 `iris/**/__init__.py` 의 Agent-readable | `pydoc` · 패치 단위 AI |
| 경계 클래스 | `UserTurnDispatcher`, `ActionRegistry` | 턴 큐 · 액션 인터페이스 |

확인:

```powershell
.venv\Scripts\python.exe -m iris.system._check_agent_readable_headers
.venv\Scripts\python.exe -m pydoc iris.runtime
```

공개 함수마다 한 줄 주석을 채우지는 않는다. AI와 기여자는 패키지 헤더로 경계를 읽고, 그다음 해당 파일을 연다.
