# Iris Agent Unified Runtime — U00 Baseline Audit

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-U00-UNIFIED-RUNTIME-BASELINE |
| 작성일 | 2026-11-24 |
| 관련 | Unified Agent Runtime, PHASE4 SpeakTools, absorbed aliases, InternalSidecar |
| 대상 | HEAD `819c42f`, PIN `a382af23f4c067d23463b5781958684c2cda82bc` |
| 목적 | 통합 런타임 착수 전 모델 대면 도구 경로·수치·실행 불일치를 고정하고 재생성 가능한 자검으로 검증한다 |

## 1. 결론

제품 말 턴은 **InternalSidecar only**다. 모델이 보는 도구는 PHASE4 SpeakAllowlist 114개에서 표면·흡수 규칙을 거친 스키마(홈/IDE 각 113개 함수명)다. Hermes 친숙명 6개(`terminal` 등)는 Control action으로 흡수되고, CORE 잔여 17개(`process_manage` 포함)는 스키마에서만 제거한다. agent_tool_registry seed 9개는 전부 `native`이며 Control action과 merge된다. 라이브 모델 벤치(Task Success / Valid Tool Call / latency / tokens)는 이번 U00에서 **미실행**이라 공란이다. 오프라인 `product_effect` 자검은 `scripts/iris_hermes_bench` 작업 디렉터리에서 통과한다.

**U05 갱신 (2026-11-24):** `process_manage` → Control `process.manage` 흡수. PHASE4=115, absorbed=7, STRIP_ONLY=16. 엔진 스키마 홈/IDE 각 114. 완료 권위는 `ExecutionRuntime` per-run 로그(`~/.iris-light/runs/<run_id>/`); `last_run.log`는 최신 compat view만. 자검: `_check_execution_runtime`, `_check_unified_runtime_baseline`.

재검증: `.venv\Scripts\python.exe -m iris.infrastructure._check_unified_runtime_baseline`

## 2. 확인한 사실

| 항목 | 값 | 증거 |
|---|---|---|
| HEAD | `819c42fc7e4271e4e00fa30eb8b4e4679090effb` | `git rev-parse HEAD` |
| Hermes / iris-agent PIN | `a382af23f4c067d23463b5781958684c2cda82bc` | `vendor/iris-agent-runtime/PIN` |
| EngineSource 기본 | `InternalSidecar` | `parse_engine_source` → 항상 sidecar |
| PHASE4 grants | 114 | `PHASE4_ALLOWLIST.grants` |
| Absorbed aliases | 6 | `ABSORBED_TOOLS` |
| STRIP_ONLY | 17 | `STRIP_ONLY_NAMES` |
| Seed registry | 9, mcp_bridge=0 | `default_registry().catalog()` |
| Surface filter | home 114 / ide 113 (`shell.run` home-only) | `HOME_ONLY_SPEAK_ACTIONS` |
| Engine schemas | home 113 / ide 113 | `engine_tool_schemas` (terminal이 shell.run·project.run을 하나로) |
| Explicit JSON schema | 12 grants | `SpeakGrant.parameters` 있는 행 |
| Bench live metrics | 공란 | 라이브 모델 벤치 미실행 |
| product_effect offline | 통과 (cwd=`scripts/iris_hermes_bench`) | `_check_product_effect` |

## 3. 구조

요청이 말 턴에서 디스크·화면·답변까지 가는 경로:

```
사용자 채팅 전송
  └─ MainWindow / ChatPanel
        └─ IrisAgentChatWorker (UI 스레드 밖)
              ├─ Engine.ensure_ready / shared_engine
              │     └─ InternalSidecar(home=~/.iris-light/agent)   ← 제품 기본 (여기가 갈림: ExternalGateway 없음)
              ├─ sidecar: _install_iris_engine_tools
              │     ├─ engine_tool_schemas(surface)
              │     │     ├─ grants_for_surface(PHASE4, home|ide_companion)
              │     │     │     └─ HOME_ONLY: shell.run 제외 (ide)
              │     │     └─ absorb: terminal/write_file/… 모델명
              │     └─ STRIP_ONLY_NAMES + Hermes CORE leftovers 제거
              ├─ 모델 툴콜
              │     ├─ absorbed resolve_action(name, surface) → Control action
              │     ├─ SpeakTools.invoke / speak_invoke_agent_tool (native seed)
              │     └─ ControlSurface.call_registered → ActionRegistry
              │           ├─ shell.run → iris_shell (PATH / cmd|/c, last_run 없음)
              │           ├─ project.run → project_ops (venv create=True, .iris/last_run.log)
              │           └─ 기타 wiki/ide/browser/…
              └─ 완료 신호 UDP done/fail → DB chat_messages → UI assistant 착지
```

갈림표:

| 갈림 | 조건 | 결과 |
|---|---|---|
| EngineSource | 제품 설정 | 항상 InternalSidecar |
| Speak surface | home vs ide_companion | `shell.run` 노출 여부, `terminal`→shell.run vs project.run |
| 툴 이름 | absorbed / PHASE4 / strip | Control로 라우트 / 스키마만 제거 |
| 실행 경로 | shell.run vs project.run | PATH 셸 vs 프로젝트 venv+last_run.log |

## 4. 코드 리뷰

| 지점 | 이번 증상·기준에서 한 일 | 요청을 막지 못한 이유 / 한계 |
|---|---|---|
| `parse_engine_source` | 제품 소스를 InternalSidecar로 고정 | Gateway 잔여는 진단·opt-in만 |
| `PHASE4_ALLOWLIST` | 모델·엔진 카탈로그 단일 손목록 114 | 102개는 default schema — 인자 계약이 느슨 |
| `grants_for_surface` | ide에서 `shell.run` 제거 | companion에서 PATH 셸 우회는 막음 |
| `ABSORBED_TOOLS` | Hermes 친숙 6명을 Control로 흡수 | `terminal`이 표면마다 다른 action |
| `STRIP_ONLY_NAMES` | `process_manage` 등 17 스키마 제거 | 업스트림 Hermes가 다시 넣으면 wire 자검이 잡음 |
| `agent_tool_registry` `_SEED` | 9 native, MCP seed 경로 금지 | 대부분 SpeakTools/Control로 이미 대체 — legacy id |
| `engine_tool_schemas` / sidecar install | 흡수명 노출 + CORE leftover 제거 | 런타임 설치 실패 시 모델에 구 Hermes명 남을 수 있음 |
| `project_ops.ensure_project_python(create=True)` | argv/file `.py` 실행 시 venv 생성 | find-only 호출과 동작이 다름 |
| `iris_shell.run_shell_job` | home `shell.run`은 PATH `cmd /c` | 프로젝트 .venv를 강제하지 않음 |
| `last_run.log` | project.run 종료코드·출력 권위 | shell.run 경로에는 없음 |
| 채팅 착지 UDP done | Turn ended → 단말 done | 이번 U00 범위 밖이나 계약 자검으로 고정 |

하지 않은 일: 제품 런타임 동작 변경, 라이브 벤치 재측정, allowlist 항목 추가·삭제.

## 5. 개선안 (빈 자리만)

1. **실행 경로 단일화** — `project.run`(create venv + last_run) vs `shell.run`(PATH) vs find-only 조회가 문서·모델 nudge와 어긋날 수 있음. 표면별 계약을 한 표로 코드 주석/자검에 묶을 자리.
2. **스키마 밀도** — 114 중 explicit 12. 위험 툴(write/run/send/delete)에 최소 required 스키마를 채울 자리.
3. **seed vs SpeakTools 이중 이름** — `iris.wiki.*` legacy와 Control `wiki.*` 공존. migrate-callers-then-delete 자리.
4. **벤치 메트릭 공란** — Task Success / Valid Tool Call / latency / tokens를 같은 PIN·HEAD에서 채울 자리(라이브 모델 필요).

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| Hermes Agent (PIN a382af23…) | 사이드카 런타임·툴 레지스트리 호스트 | 제품 Speak 경로는 Iris Control; CORE 툴셋은 strip/absorb |
| serin `iris/engine` | InternalSidecar·install·types | 이미 흡수됨; in-process AIAgent 전체는 비제품 |
| Iris `SpeakAllowlist` / absorbed aliases | 모델 대면 계약의 권위 | 신규 툴 추가 없이 U00 고정만 |
| MCP iris-control | compat HTTP 잔여 | 제품 speak는 native; seed MCP bridge=0 유지 |
| `scripts/iris_hermes_bench` | product_effect 채점·페이즈 케이스 | 라이브 모델 턴은 U00에서 미실행 |
| process_manage (Hermes) | process.manage | U05 흡수 — ExecutionRuntime (Local Subprocess) |

## 7. 모델 대면 도구 인벤토리

### 7.1 PHASE4_ALLOWLIST (114)

| model name | control action | schema | decision | kind | surface | related files | existing tests |
|---|---|---|---|---|---|---|---|
| `app_demo_ping` | `app.demo_ping` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `app_directory_list` | `app.directory_list` | default | keep | pure | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `attachment_copy_to` | `attachment.copy_to` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `attachment_move_to` | `attachment.move_to` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_back` | `browser.back` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_click` | `browser.click` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_extract` | `browser.extract` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_forward` | `browser.forward` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_media` | `browser.media` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_mini_player` | `browser.mini_player` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_navigate` | `browser.navigate` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_open` | `browser.open` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_reload` | `browser.reload` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_scroll` | `browser.scroll` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_search` | `browser.search` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_snapshot` | `browser.snapshot` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `browser_type` | `browser.type` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `calendar_add_event` | `calendar.add_event` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `calendar_delete_event` | `calendar.delete_event` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `calendar_list_events` | `calendar.list_events` | default | keep | pure | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `calendar_refresh_holidays` | `calendar.refresh_holidays` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `calendar_select_day` | `calendar.select_day` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `calendar_set_month` | `calendar.set_month` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `calendar_status` | `calendar.status` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `chat_exec_python` | `chat.exec_python` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `chat_new_session` | `chat.new_session` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `chat_search_past` | `chat.search_past` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `content_dump_lab_scripts` | `content.dump_lab_scripts` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `content_extract` | `content.extract` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `diagram_render` | `diagram.render` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `email_list_accounts` | `email.list_accounts` | default | keep | pure | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `email_list_messages` | `email.list_messages` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `email_open_compose` | `email.open_compose` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `email_read_message` | `email.read_message` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `email_send` | `email.send` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_input_text` | `emulator.input_text` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_install` | `emulator.install` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_key` | `emulator.key` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_kill` | `emulator.kill` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_launch` | `emulator.launch` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_logcat_tail` | `emulator.logcat_tail` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_play_install` | `emulator.play_install` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_screenshot` | `emulator.screenshot` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_start_app` | `emulator.start_app` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_status` | `emulator.status` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_swipe` | `emulator.swipe` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_tap` | `emulator.tap` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_tap_text` | `emulator.tap_text` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_ui_texts` | `emulator.ui_texts` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `emulator_wait_ready` | `emulator.wait_ready` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `extension_install_github` | `extension.install_github` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `get_catalog` | `get_catalog` | default | keep | pure | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `get_state` | `get_state` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_debug` | `ide.debug` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_definition` | `ide.definition` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_diagnostics` | `ide.diagnostics` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_edit` | `ide.edit` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_enter_companion` | `ide.enter_companion` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_exit_companion` | `ide.exit_companion` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_marketplace_install` | `ide.marketplace_install` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_marketplace_search` | `ide.marketplace_search` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_open_file` | `ide.open_file` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_open_folder` | `ide.open_folder` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_project_log` | `ide.project_log` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_references` | `ide.references` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_save` | `ide.save` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_symbols` | `ide.symbols` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ide_task` | `ide.task` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `learning_list` | `learning.list` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `learning_run` | `learning.run` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `learning_start` | `learning.start` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `learning_status` | `learning.status` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `learning_stop` | `learning.stop` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `local_read_file` | `local.read_file` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `search_files` | `local.search_files` | explicit | absorb→search_files | surface | both | `speak_capability.py` | `_check_speak_tools_phase4`, `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `note_export_pdf` | `note.export_pdf` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `ping` | `ping` | default | keep | pure | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `project_create_scaffold` | `project.create_scaffold` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `project_delete` | `project.delete` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `project_import_attachment` | `project.import_attachment` | explicit | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `project_list_files` | `project.list_files` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `project_list_parents` | `project.list_parents` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `project_open_similar` | `project.open_similar` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `read_file` | `project.read_file` | default | absorb→read_file | surface | both | `speak_capability.py` | `_check_speak_tools_phase4`, `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `project_rename_file` | `project.rename_file` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `terminal` | `project.run` | default | absorb→terminal | surface | both | `speak_capability.py` | `_check_speak_tools_phase4`, `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `write_file` | `project.write_file` | default | absorb→write_file | surface | both | `speak_capability.py` | `_check_speak_tools_phase4`, `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `project_write_image_code` | `project.write_image_code` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `routine_create` | `routine.create` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `routine_delete` | `routine.delete` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `routine_list` | `routine.list` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `routine_run` | `routine.run` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `routine_update` | `routine.update` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `settings_get` | `settings.get` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `terminal` | `shell.run` | explicit | absorb→terminal | surface | home-only | `speak_capability.py` | `_check_speak_tools_phase4`, `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `voice_mic_off` | `voice.mic_off` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `voice_mic_on` | `voice.mic_on` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `voice_mic_status` | `voice.mic_status` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `voice_toggle_mic` | `voice.toggle_mic` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `web_extract` | `web.run_extract` | explicit | absorb→web_extract | surface | both | `speak_capability.py` | `_check_speak_tools_phase4`, `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `web_search` | `web.run_search` | explicit | absorb→web_search | surface | both | `speak_capability.py` | `_check_speak_tools_phase4`, `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `wiki_import_content` | `wiki.import_content` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `wiki_import_pages` | `wiki.import_pages` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `wiki_list_notes` | `wiki.list_notes` | default | keep | pure | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `wiki_move_notes` | `wiki.move_notes` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `wiki_open_note` | `wiki.open_note` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `wiki_reload` | `wiki.reload` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `wiki_search` | `wiki.search` | default | keep | pure | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `wiki_write_user_note` | `wiki.write_user_note` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `workspace_open_assistant` | `workspace.open_assistant` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `workspace_open_calendar` | `workspace.open_calendar` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `workspace_open_email` | `workspace.open_email` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `workspace_open_mobile` | `workspace.open_mobile` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |
| `workspace_open_obsidian` | `workspace.open_obsidian` | default | keep | surface | both | `speak_capability.py` | `_check_speak_tools_phase4` |

### 7.2 Absorbed 6 aliases

| model name | control action | schema | decision | related files | existing tests |
|---|---|---|---|---|---|
| `terminal` | home→`shell.run` / ide_companion→`project.run` | via target grant | absorb | `absorbed_tool_aliases.py`, `speak_capability.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `write_file` | `project.write_file` | via target grant | absorb | `absorbed_tool_aliases.py`, `speak_capability.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `read_file` | `project.read_file` | via target grant | absorb | `absorbed_tool_aliases.py`, `speak_capability.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `search_files` | `local.search_files` | via target grant | absorb | `absorbed_tool_aliases.py`, `speak_capability.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `web_search` | `web.run_search` | via target grant | absorb | `absorbed_tool_aliases.py`, `speak_capability.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `web_extract` | `web.run_extract` | via target grant | absorb | `absorbed_tool_aliases.py`, `speak_capability.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `process_manage` | `process.manage` | via target grant | absorb (U05) | `absorbed_tool_aliases.py`, `execution_runtime.py` | `_check_execution_runtime`, `_check_absorbed_tool_aliases` |

### 7.3 STRIP_ONLY_NAMES (16 after U05; was 17)

| model name | control action | schema | decision | related files | existing tests |
|---|---|---|---|---|---|
| `clarify` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `computer_use` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `cronjob_manage` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `delegate_task` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `execute_code` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `image_generate` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `manage_connections` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `memory` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `patch` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `session_search` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `skill_manage` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `skill_view` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `skills_list` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `text_to_speech` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `todo_list` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |
| `vision_analyze` | — (none) | stripped | strip | `absorbed_tool_aliases.py` | `_check_absorbed_tool_aliases`, `_check_absorbed_tool_wire` |

### 7.4 agent_tool_registry seed (9)

| model/product name | control action | schema | decision | related files | existing tests |
|---|---|---|---|---|---|
| `iris.calendar.list_events` | `calendar.list_events` | native handler | merge→Control `calendar.list_events` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.ide.open_folder` | `ide.open_folder` | native handler | merge→Control `ide.open_folder` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.mail.list_accounts` | `email.list_accounts` | native handler | merge→Control `email.list_accounts` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.project.open_similar` | `project.open_similar` | native handler | merge→Control `project.open_similar` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.session.get_state` | `get_state` | native handler | merge→Control `get_state` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.tools.catalog` | `get_catalog` | native handler | merge→Control `get_catalog` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.tools.ping` | `ping` | native handler | merge→Control `ping` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.wiki.list_notes` | `wiki.list_notes` | native handler | merge→Control `wiki.list_notes` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |
| `iris.wiki.search` | `wiki.search` | native handler | merge→Control `wiki.search` (legacy seed id) | `agent_tool_registry.py` | `_check_iris_agent_tool_registry_phase2*`, `_check_speak_tools_no_mcp_seed_path` |

### 7.5 Surface filter

| surface | grants | engine schemas | 규칙 |
|---|---|---|---|
| `home` | 114 | 113 | 전체 PHASE4. `terminal`→`shell.run` (project.run은 스키마에서 가려짐) |
| `ide_companion` | 113 | 113 | `shell.run` 제외. `terminal`→`project.run` |

관련: `grants_for_surface`, `HOME_ONLY_SPEAK_ACTIONS={"shell.run"}`, `engine_tool_schemas`.
자검: `_check_speak_surface_shell`, `_check_absorbed_tool_wire`.

## 8. 실행 경로 불일치 (기지)

| 경로 | Python/해석기 | 출력 권위 | 비고 |
|---|---|---|---|
| `project.run` + argv/`*.py` | `ensure_project_python(create=True)` — 없으면 **venv 생성** | `.iris/last_run.log` + `IRIS_EXIT` | IDE 바인딩 터미널 |
| `find_project_venv_python` / `create=False` | **find-only**, 없으면 None | — | 조회·자검용 |
| `shell.run` (home) | `cmd /c` 또는 `sh -c` → **프로세스 PATH** | 채팅 카드 stdout/stderr 클립 | last_run.log 없음 |
| `process_manage` / `process.manage` | Local Subprocess (`ExecutionRuntime`) | per-run `stdout.log`/`stderr.log` (+ `last_run.log` compat) | U05 흡수; IDE `project.run` 브리지는 GUI UX 유지 |

## 9. Bench metrics (U00)

| 지표 | 값 | 이유 |
|---|---|---|
| Task Success | — | 라이브 모델 벤치 미실행 |
| Valid Tool Call | — | 동일 |
| latency | — | 동일 |
| tokens | — | 동일 |
| product_effect (offline grader) | ok | `scripts/iris_hermes_bench/_check_product_effect.py` |

과거 참고(수치 재사용 금지, 맥락만): `docs/code-review/IRIS-Hermes-벤치마크-4페이즈-결과.md` (2026-11-09, 다른 HEAD/세션).

## 10. 자검·재생성

```powershell
.venv\Scripts\python.exe -m iris.infrastructure._check_unified_runtime_baseline
.venv\Scripts\python.exe -m iris.ui._check_chat_landing_contract
.venv\Scripts\python.exe -m iris.infrastructure._check_absorbed_tool_aliases
.venv\Scripts\python.exe -m iris.infrastructure._check_absorbed_tool_wire
.venv\Scripts\python.exe -m iris.system._check_speak_tools_phase4
.venv\Scripts\python.exe -m iris.system._check_iris_agent_absorbed_toolsets
Set-Location scripts\iris_hermes_bench; ..\..\.venv\Scripts\python.exe _check_product_effect.py
```

## 11. 조치

1. 본 문서와 `_check_unified_runtime_baseline`으로 U00 수치를 고정한다.
2. 통합 런타임 후속 단계에서는 인벤토리 카운트가 바뀌면 자검 EXPECTED_* 와 본 표를 함께 갱신한다.
3. 라이브 벤치가 가능해지면 §9 공란만 채운다 (추정 숫자 금지).

## 12. Wave 1 착지 (U00–U06, 2026-11-24)

| 항목 | Wave 1 후 (자검) |
|---|---|
| PHASE4 / absorbed / strip | 116 / 8 / 15 |
| 흡수 추가 | `process_manage` → `process.manage`, `apply_patch` → `project.apply_patch` |
| Schema chars | home 22385 / ide 22126 |
| 신규 모듈 | `execution_policy`, `workspace_env`, `execution_runtime`, `file_patch`, tool contract |
| 후속 브리프 | [wave2](iris-agent-unified-runtime-wave2-brief.md), [wave3](iris-agent-unified-runtime-wave3-brief.md) |

U00 인벤토리 표(§7)는 당시 스냅샷이다. 현재 숫자는 `_check_unified_runtime_baseline`을 재실행한다.
