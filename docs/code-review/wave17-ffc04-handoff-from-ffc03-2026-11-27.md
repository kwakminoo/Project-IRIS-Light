# FFC-04 인수인계 (from FFC-03)

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FFC04-HANDOFF-FROM-03 |
| 작성일 | 2026-11-27 |
| 관련 | [FFC-03 흡수 보고](wave17-ffc03-functional-absorption-2026-11-27.md) |
| 대상 | FFC-04 Gateway/Connector 및 FFC-03 실모델 잔여 |
| 목적 | 03에서 닫지 않은 정확한 항목만 넘긴다 |

## 1. 결론

FFC-03은 Native 흡수·host 증거·정직 status까지 L2/L3로 닫았다 (`home_n=131`, STRIP=`memory`만). 04로 넘기는 것은 (A) 03 실모델/UX 잔여와 (B) 원래 FRC-04A/B Gateway·Connector 범위다. 미구현을 L2 PASS로 숨기지 않는다.

## 2. FFC-03에서 남은 정확한 항목

| ID | 항목 | 완료 기준 |
|---|---|---|
| H03-L4-TODO | 실모델: todo upsert → 도구 실행 → host mint → complete | DB/UI에 completed + ledger token 증거 |
| H03-L4-CLARIFY | 실모델: clarify open → 사용자 답 → ResumeTicket → 턴 재개 | ChatPanel/Speak resume 경로 |
| H03-L4-DELEGATE | 실모델: delegate spawn → 자식 결과 aggregate | 세션 혼입 없음, cancel 시 orphan 없음 |
| H03-UX-CLARIFY | ChatPanel이 ResumeTicket으로 followthrough 재개 | 질문 텍스트만으로 완료 처리 금지 |
| H03-DELEGATE-LAND | 자식 Engine 결과 채팅 착지 + cancel→sidecar 종료 | iris-agent-chat-landing 계약 |
| H03-TTS-IMG | Provider 실호출(승인 후) | status-only에서 승격; 가짜 bytes 금지 |
| H03-CONN-RECONNECT | connections.reconnect 승인 액션 | 토큰 비노출 유지 |
| H03-CRON-LIVE | routine.manage 격리 fixture 예약 실행 | 부작용 중복 없음 |

## 3. FFC-04 고유 (기존 FRC-04)

| ID | 항목 |
|---|---|
| FRC-04A | 서명 Webhook·공용 Connector 진입 |
| FRC-04B 잔여 | dual-server isolation, stdio reconnect, 거부·취소·단절 조합, 실모델 MCP |

## 4. 하지 말 것

- `_guard_hermes_registry_dispatch` / `_skip_mcp_refresh` 무단 해제
- Hermes `memory` umbrella 스키마 재도입 (FFC-02 `memory_*` 정본)
- computer_use에 raw desktop 지원 표기
- image/tts 고정 가짜 결과
- Wave 2 고급 multi-agent를 03 완료로 가장

## 5. 재검증 명령 (회귀)

```
.venv\Scripts\python.exe -m iris.infrastructure._check_ffc03_residual_absorb
.venv\Scripts\python.exe -m iris.infrastructure._check_absorbed_tool_wire
.venv\Scripts\python.exe -m iris.infrastructure._check_tool_contract
.venv\Scripts\python.exe -m iris.infrastructure._check_native_tool_hermes_disabled
.venv\Scripts\python.exe -m iris.runtime._check_todo_manage_host
.venv\Scripts\python.exe -m iris.runtime._check_clarify_manage_host
.venv\Scripts\python.exe -m iris.runtime._check_delegate_manage_host
```

## 6. 조치

1. 04 착수 시 H03-L4-*를 Gateway와 분리된 검증 단위로 둘 것.
2. L4 PASS 증거는 `.tmp/ffc-03/` 아래에 json으로 남길 것.
