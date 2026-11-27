# FRC-02 Functional Absorption Binding Inventory

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FRC-02-INV-2026-11-27 |
| 작성일 | 2026-11-27 |
| 관련 | [FRC tracker](wave17-frc-tracker-2026-11-27.md), [흡수표](wave17-fc-functional-absorption.md) |
| 대상 | Hermes 15행 → Iris Speak/Control 바인딩 |
| 목적 | BOUND/ALIAS_ONLY/MISSING/BLOCKED 전수와 이번 세션 폐쇄 범위 |

## 1. 결론

15행 중 3개를 기존 Control/Speak 액션에 Hermes 익숙 이름으로 흡수했다 (`skills_list`, `skill_view`, `vision_analyze`). 스키마 개수는 `home_n=119` 유지(이름만 교체). `session_search` 등 나머지는 새 제품 면 없이 안전하게 닫을 수 없어 보류했다. `clarify` / Hermes `apply_patch`·`patch` 원본 디스패치는 계속 차단이다.

## 2. 인벤토리 (15)

| hermes_name | iris_action_or_path | binding_state | evidence_command | live_verified | residual_note |
|---|---|---|---|---|---|
| `vision_analyze` | `vision.analyze_attachment` (`iris/ui/control_actions/wiki.py`) | BOUND | `python -m iris.infrastructure._check_absorbed_tool_wire` | true | FRC-02 흡수. 스키마 이름 `vision_analyze`(구 `vision_analyze_attachment`). 실 Vision 모델 품질은 잔여. |
| `image_generate` | Vendor 제공자만, SpeakGrant 없음 | MISSING | `engine_tool_schemas`에 이름 없음 | false | Native Speak/Control 액션 없음. 제품 면 신설 없이는 불가. |
| `skills_list` | `skill.list` (`iris/ui/control_actions/learning.py`) | BOUND | `python -m iris.infrastructure._check_absorbed_tool_aliases` | true | FRC-02 흡수. 구 스키마 `skill_list` → `skills_list`. |
| `skill_view` | `skill.view` | BOUND | 동일 aliases + wire | true | FRC-02 흡수(이미 underscore로 노출되던 이름을 registry에 고정). |
| `skill_manage` | `skill.manage` (SpeakGrant + Control) | ALIAS_ONLY | 스키마 `skill_manage` = `engine_tool_name(skill.manage)` | false | Control/Speak는 있음. Hermes strip 잔여·승인 계약은 유지. AbsorbedTool 미등록(이번 3건 한도). |
| `text_to_speech` | Desktop Voice/TTS 큐, Speak는 mic만 | MISSING | SpeakGrant에 TTS speak/play 없음 | false | mic on/off만 Speak. 모델 TTS 액션 신설 필요 → 비대상. |
| `todo_list` | 턴 활동 UI만 | MISSING | strip + 스키마 없음 | false | Native 태스크 API는 FRC-03. |
| `memory` | `wiki.search` / `wiki.write_user_note` 등 | ALIAS_ONLY | 스키마 `wiki_search` 등 | false | Wiki 도구로 부분 대체. Hermes `memory` CRUD 단일 도구 없음 → FRC-03. |
| `session_search` | `chat.search_past` | ALIAS_ONLY | 스키마 `chat_search_past` | false | **이번 미배선.** `IRIS_EAGER_MODEL_TOOLS`가 `chat_search_past`를 핀(FRC-01 `tool_surface.py`). 이름 바꾸면 eager/compact 회귀. |
| `clarify` | ChatPanel 후속 질의 | BLOCKED | `_check_native_tool_hermes_disabled` | false | strip + 스키마 없음. 대기/재개는 FRC-03. |
| `execute_code` | `terminal`→`shell.run`/`project.run`, `process.manage` | ALIAS_ONLY | absorbed `terminal`/`process_manage` | false | 셸·프로세스 경로로 대체. 범용 인라인 코드 도구는 잔여. |
| `delegate_task` | `Engine.fork()` | MISSING | Speak/Control 모델 도구 없음 | false | 권한·예산·취소는 FRC-03. |
| `cronjob_manage` | `routine.create`/`list`/`run`/`update`/`delete` | ALIAS_ONLY | 스키마 `routine_*` | false | 다액션 Routine 면. 단일 Hermes cron 도구 흡수는 제품 설계 필요. |
| `computer_use` | browser / emulator / learning Speak 묶음 | ALIAS_ONLY | 개별 제품 도구 | false | 통합 observe→act→cancel 계약 잔여. 단일 도구 신설 금지. |
| `manage_connections` | MCP Native Manager / Gateway 토큰 API | MISSING | 모델 Speak 단일 관리 도구 없음 | false | UI·설정 경로만. Connector 재연결 모델 계약 잔여. |

행 형식 원형: `{hermes_name, iris_action_or_path, binding_state, evidence_command, live_verified, residual_note}`.

## 3. 이번 세션 배선

| Hermes | Control | 변경 위치 |
|---|---|---|
| `skills_list` | `skill.list` | `iris/infrastructure/absorbed_tool_aliases.py` |
| `skill_view` | `skill.view` | 동일 |
| `vision_analyze` | `vision.analyze_attachment` | 동일 |

체크 갱신: `_check_absorbed_tool_aliases.py`, `_check_absorbed_tool_wire.py`.

### 검증 (측정)

```
python -m iris.infrastructure._check_absorbed_tool_aliases   # ok
python -m iris.infrastructure._check_absorbed_tool_wire      # ok home_n=119 ide_n=119
python -m iris.infrastructure._check_tool_contract           # ok engine_schema_home_count=119
python -m iris.infrastructure._check_native_tool_hermes_disabled  # blocked=apply_patch,clarify,patch
python -m iris.infrastructure._check_native_tool_binding     # ok
```

## 4. Not wireable now

| 후보 | 이유 |
|---|---|
| `session_search` → `chat.search_past` | FRC-01 eager 핀 `chat_search_past`. 흡수 시 `tool_surface.py` 동시 수정 필요(이번 FRC-01 동결). |
| `skill_manage` AbsorbedTool화 | Speak는 이미 `skill_manage`. 3건 한도·승인 면은 추가 설계 없이 strip 유지. |
| `image_generate` / `text_to_speech` / `todo_list` / `delegate_task` / `manage_connections` | Speak/Control 정본 없음 또는 FRC-03+ 범위. |
| `memory` / `cronjob_manage` / `computer_use` / `execute_code` | 다액션·부분 대체만 존재. 단일 Hermes 이름 흡수는 제품 면 설계. |
| `clarify` | 명시 BLOCKED. |

## 5. 조치

1. FRC tracker에 FRC-02 부분 진행(3/15 Hermes 이름 흡수, 인벤토리 완료) 반영은 상위 조율에 맡김.
2. `session_search` 흡수는 FRC-01 `IRIS_EAGER_MODEL_TOOLS` 갱신과 한 묶음으로만.
3. FRC-03+ 착수하지 않음.
