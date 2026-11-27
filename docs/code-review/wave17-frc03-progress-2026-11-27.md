# FRC-03 progress (2026-11-27)

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FRC03-PROGRESS |
| 작성일 | 2026-11-27 |
| 관련 | FRC-03 · Wave 1.7 FINAL RESIDUAL |
| 대상 | Owned loop / turn context / todo evidence / memory / clarify / delegate |
| 목적 | 한 단위만 닫고 잔여를 분리 |

## 1. 결론

이번 단위는 **Todo 완료 증거**만 닫았다. 세션 스코프 `TurnTodoStore`가 `completed`에 비어 있지 않은 `TodoEvidence`를 강제한다. Speak·UI·Engine.fork·기억 CRUD·clarify 재개는 아직 열리지 않았다.

## 2. 이미 있던 것

| 부품 | 역할 | FRC-03와의 거리 |
|---|---|---|
| `ExecutionContext` + `_check_execution_context` | 턴 고정 ACL·신뢰 필드 | 턴 신원은 있음. 오케스트레이션 상태 저장소는 없음 |
| `tests/test_wave17_turn_context.py` | 동결 컨텍스트·취소·동시 턴 | NGI-03 핫패스. 재시작 영속화는 잔여 |
| `turn_followthrough` / `TurnEvidence` | 모델 문장 ≠ 도구/디스크 증거 | 파일·위키 허위완료 게이트. todo 목록 계약은 없음 |
| `ChatRunSlot` | 대화별 슬롯·tool_ok_count | 세션 맵은 있음. todo/clarify 상태 머신 없음 |
| `Engine.fork` | 독립 sidecar 핸들 | 하위 권한·예산·취소 제품 없음 (이번 비대상) |
| Hermes `todo_list` / `clarify` / `memory` / `delegate_task` | vendor 도구 | strip·MISSING·BLOCKED → FRC-03 잔여 |

## 3. 이번에 닫은 것

| 항목 | 내용 |
|---|---|
| 데이터 형태 | `TodoEvidence(kind, detail)` · `TodoItem` · `TurnTodoStore(session_id)` |
| 계약 | `completed`는 `require_completion_evidence` 통과만. 빈 kind/detail·취소 후 complete 거부 |
| 파일 | `iris/runtime/turn_todo.py` · `iris/runtime/_check_turn_todo_evidence.py` |
| 검증 | `python -m iris.runtime._check_turn_todo_evidence` |

## 4. FRC-03 잔여

1. Speak/Control에 todo 액션 배선 (strip `todo_list` 대체) — FRC-02와 겹치지 않게 aliases 소유권 주의
2. 기억 CRUD (Wiki 소유 유지, Hermes `memory` 단일 도구 대체)
3. clarify 입력 대기/재개 훅 (ChatPanel 후속 · followthrough `ask`와 연결)
4. delegate 권한·예산·취소 수명주기 (`Engine.fork` 제품화는 별 단위)
5. 턴 컨텍스트 재시작 영속화 / 외부 세션 소유권 (NGI-03 잔여)

## 5. 조치

1. 자검 green 유지.
2. 다음 최소 단위는 clarify await/resume 순수 상태 또는 memory CRUD 중 하나.
3. Engine.fork 제품·FRC-04+ 착수하지 않음.
