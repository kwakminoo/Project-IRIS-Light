# FFC-03 Hermes Functional Absorption Closure

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FFC03-ABSORB-2026-11-27 |
| 작성일 | 2026-11-27 |
| 관련 | [FFC tracker](wave17-ffc-tracker.md), [FRC-02 inventory](wave17-frc02-binding-inventory-2026-11-27.md), 프롬프트 `03_FFC_Functional_Absorption` |
| 대상 | Hermes 15행 → Iris Native Speak/Control |
| 목적 | alias-only로 끝내지 않고 host-attested 실행 경로와 정직한 잔여를 닫기 |

## 1. 결론

15행 중 Native 흡수·동등·정직 status를 닫았다. `home_n=131`. Hermes umbrella `memory`만 STRIP(의도: FFC-02 `memory_*` 정본). Todo 완료는 host mint 토큰만 통과한다. Clarify resume는 `ResumeTicket`만 성공으로 친다. Delegate는 `shared_engine().fork()` factory를 탄다. image/tts는 가짜 바이트 없이 status. L2/L3 계약 자검 PASS. Todo/Clarify/Delegate의 실모델 L4는 이번 세션 미실행 → 04 인수인계.

## 2. 확인한 사실 (측정)

```
ffc03_residual_absorb ok home_n=131 strip=['memory']
absorbed_tool_wire ok home_n=131
tool_contract ok engine_schema_home_count=131
native_tool_hermes_disabled ok blocked=apply_patch,patch
todo_manage_host / clarify_manage_host / delegate_manage_host ok
tool_surface ok
unittest tests.test_wave17_memory OK (3)
```

Desktop `IRIS.lnk` → `dist\IRIS.exe` (thin launcher).

## 3. 15행 상태

| hermes_name | canonical | binding | L2 | L3 | L4 | L5 | note |
|---|---|---|---|---|---|---|---|
| vision_analyze | vision.analyze_attachment | BOUND | PASS | PASS | prior FRC-02 | — | 품질 잔여 |
| image_generate | image.status | BOUND (status) | PASS | PASS | n/a provider | — | 가짜 payload 금지 |
| skills_list | skill.list | BOUND | PASS | PASS | prior | — | FRC-02 |
| skill_view | skill.view | BOUND | PASS | PASS | prior | — | FRC-02 |
| skill_manage | skill.manage | BOUND | PASS | PASS | 미실행 | — | confirm 유지 |
| text_to_speech | voice.tts_status | BOUND (status) | PASS | PASS | n/a provider | — | mic≠TTS |
| todo_list | todo.manage | BOUND | PASS | PASS | **미실행** | — | host evidence_token |
| memory | memory.* (FFC-02) | STRIP umbrella | PASS | PASS | FFC-02 PASS | PASS | 중복 저장소 없음 |
| session_search | chat.search_past | BOUND | PASS | PASS | 미실행 | — | eager=`session_search` |
| clarify | clarify.manage | BOUND | PASS | PASS | **미실행** | — | ResumeTicket |
| execute_code | terminal (INTERNAL) | BOUND | PASS | PASS | prior shell | — | 인라인 executor 없음 |
| delegate_task | delegate.manage | BOUND | PASS | PASS | **미실행** | — | Engine.fork factory |
| cronjob_manage | routine.manage | BOUND | PASS | PASS | 미실행 | — | dispatcher only |
| computer_use | computer.surfaces | BOUND | PASS | PASS | n/a | — | raw_desktop unsupported |
| manage_connections | connections.status | BOUND | PASS | PASS | 미실행 | — | 비시크릿 |

L2=계약/스키마 자검. L3=host Control 경로. L4=실모델 턴. L5=GUI/제품 시나리오.

## 4. 구조

```
Model tool name
  → AbsorbedTool / INTERNAL_ALIASES / SpeakGrant
  → engine_tool_schemas / bindings (home_n=131)
  → sidecar handle_function_call
  → Control action (todo/clarify/delegate/routine/connections/…)
  → domain store (TurnTodoStore+ledger / ClarifyWaitStore / DelegateSessionRegistry)
  → ToolResult (host meta; no forged complete)
```

분기: STRIP `{memory}` · blocked Hermes `{apply_patch, patch}` · `_guard_hermes_registry_dispatch` 유지.

## 5. 코드 리뷰 (경로 지점)

| 지점 | 이번 증상에서 한 일 | 막지 못한/남긴 것 |
|---|---|---|
| turn_todo + HostEvidenceLedger | 완료 kind/token host-only | UI confirm mint 핫패스 실배선 얇음 |
| todo.manage Control | list/upsert/complete+token | 실모델 todo→tool→mint L4 없음 |
| clarify_wait + clarify.manage | ResumeTicket 강제 | ChatPanel 자동 resume UX |
| delegate_session + delegate.manage | grants∩·fork factory | 자식 턴 채팅 착지·예산 실시간 집행 |
| tool_surface eager | chat_search_past→session_search | — |
| image/tts status | 미설치 정직 보고 | 유료 Provider 실호출(승인 후) |
| 하지 않은 일 | Wave2 multi-agent 협업, registry 가드 해제 | — |

## 6. 개선안 (구조 빈자리만)

1. 실모델 L4: todo 생성→도구 ok→mint complete, clarify await→user resume, delegate spawn→aggregate.
2. ChatPanel이 Clarify `ResumeTicket`으로 턴 재개.
3. Delegate 자식 결과의 DB/UI 착지와 cancel→sidecar 실종료 강화.
4. image/tts Provider 실경로(승인·과금 경계).
5. connections.reconnect 승인 액션(status만 있음).

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| 기존 Iris Routine/Speak | cron dispatcher | 새 스케줄러 불필요 |
| Engine.fork | delegate factory | Hermes registry 우회 금지 |
| FFC-02 MemoryStore | 기억 정본 | 중복 CRUD 도구 금지 |
| 찾지 못함 | desktop computer-use 통합 관측→실행 OS API | 제품 면 미지원 → unsupported 명시 |

## 8. 조치

1. L2/L3 자검 green 유지.
2. L4 실모델·ChatPanel resume·delegate 착지는 [04 인수인계](wave17-ffc04-handoff-from-ffc03-2026-11-27.md).
3. 커밋/push는 사용자 요청 시에만.
