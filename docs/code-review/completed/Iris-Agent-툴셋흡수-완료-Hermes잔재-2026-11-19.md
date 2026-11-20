# Iris Agent 툴셋 흡수 완료 · Hermes 잔재 점검

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-19-FAMILIAR-ABSORB |
| 작성일 | 2026-11-19 |
| 관련 | `docs/prompts/completed/Iris-Agent-툴셋흡수-익숙한이름-구현프롬프트.md`, Units 0–6 |
| 대상 | familiar 카탈로그 · Speak fold · nudge · `:8642` · 남은 Hermes 일체화 |
| 목적 | 흡수 완료 사실과 아직 남은 Hermes/미흡수 표면을 한 장에 고정 |

## 1. 결론

제품 채팅 경로에서 file/terminal은 **익숙한 이름 + Iris Control**로 흡수됐다. web은 **Hermes upstream 유지**. Speak 겹침 이름과 사용자 노출 `:8642` 기본 함의는 걷었다. 채팅은 InternalSidecar로 착지한다.

아직 남은 것은 **브랜딩·API 심볼·이중 노출 일부·환경변수에 박힌 옛 URL·프로세스 병합 금지 범위**다. 이번 프롬프트 Out of scope와 일치한다.

**2026-11-20:** Speak fold(§5.1)와 `agent_command` 브랜딩 기본값은 코드에 반영됨. 남은 화장품 브랜딩만 후순위 보류.

## 2. 확인한 사실 (증거)

| 사실 | 근거 |
|---|---|
| Unit 0–6 자검 green | `_check_familiar_*`, `_check_familiar_speak_fold`, `_check_familiar_web_keep`, `_check_no_user_facing_8642`, `_check_no_product_gateway_ops` |
| 라이브 채팅 착지 | `.iris_light_test_tmp/verify-iris/absorb-u*` land.json (예: u6 `LAND_OK` assistant `OK`) |
| 코드 기본 `agent_base_url` | `Settings.agent_base_url == ""` |
| 런타임 `load_settings()` env | **AGENT-only.** `IRIS_HERMES_*`는 읽지 않음. `IRIS_AGENT_BASE_URL`에 `:8642`가 있으면 strip → `""` (sidecar-only). HERMES-only `:8642`는 제품 URL에 반영되지 않음 |
| Phase1 Merge 미실시 | Qt same-process AIAgent 없음 |

## 3. 구조

```
채팅 전송
  → InternalSidecar (_sidecar_main)
       → AIAgent(disabled_toolsets=[file, terminal])
       → Speak schemas (fold: project_write/read/list, shell_run, local_write, control_invoke)
       → familiar_tools (_load_local_helper) → write_file/read_file/search_files/terminal
            → adapt_control_invoke(surface) → Control invoke
       → Hermes web_search/web_extract (upstream keep)
  → UDP done → UI land DB
```

이번 요청이 갈라진 곳: **모델 메뉴 이름** (familiar) vs **실행** (Iris Control) vs **검색** (Hermes web) vs **게이트웨이** (제품 기동 금지).

## 4. 코드 리뷰 (흡수 경로)

| 지점 | 이번 흡수에서 한 일 | 막지 못한 / 남은 일 |
|---|---|---|
| `familiar_tools.py` | 매핑·adapter·fold 맵 | 없음 (정본) |
| `_sidecar_main` | file/terminal disable + familiar Iris 등록; 파일 로드로 PyQt6 회피 | live tools 목록 직접 덤프 자검은 scrape 수준 |
| `speak_capability` | model schema fold | `local_read_file` / `local_search_files` / `project_run` 등은 모델에 남을 수 있음 |
| `local.write_file` | home write Control | HTTP 호출은 `confirm_required` HUD |
| MEMORY nudge v45 | familiar FS/shell 가르침 | SpeakTools 총론·브라우저 “built-in 금지” 설교 잔존 |
| settings / UI `:8642` | 코드 기본·카피 청소; AGENT URL의 `:8642` strip | 디스크 `.env`에 남은 `IRIS_HERMES_*` 문자열(제품은 미읽음), gateway·setup 진단, `agent_command="hermes"` |

### 하지 않은 일
- Qt in-process AIAgent merge (Phase1 NO-GO)
- pin/Nous 전체 리네임, `hermes_*` API 전부 삭제
- Speak web 스택 재구축
- 사용자 환경변수의 `:8642` 강제 삭제

## 5. 개선안 (빈 자리만)

> Speak fold(§5.1)·`agent_command` 기본값: **DONE (2026-11-20)**. 아래 1–2는 남은 화장품만.

1. **이중 노출 접기 확장** — `local_read_file` / `local_search_files` / `project_run`을 familiar와 겹치면 fold.
2. **브랜딩 PR** — `hermes_update`, `hermes_home`, `load_hermes_tool_choice`, setup `hermes_*` 스텝 이름 (기본 `agent_command`는 반영됨).
3. **환경 잔재 안내** — 디스크에 남은 `IRIS_HERMES_*`는 이미 미읽음. `IRIS_AGENT_BASE_URL`의 `:8642`는 strip됨. 사용자 `.env` 정리·안내만 남음.
4. **main_window / setup_wizard** — 옛 terminal/gateway 문구·진단 UI 정리 (기능 유지 시 라벨만 Iris Agent).

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| Hermes AIAgent toolsets | web_search/web_extract 핸들러 | 이미 keep-upstream; Speak web 불필요 |
| Cursor/Theia tool naming | familiar 이름 UX | 매핑 테이블로 충분; 추가 프레임워크 불필요 |
| 별도 MCP iris-control | 모델 탈출구 | 제품 Speak/Control로 대체됨; 재도입 금지 |

## 7. 백로그 CLOSED (병합하지 않음)

| 항목 | 판정 | 잠금 |
|---|---|---|
| Slot D — Hermes file/terminal | **CLOSED: REPLACE** (MERGE 아님) | sidecar `disabled_toolsets=["file","terminal"]` + Iris `model_tool_names` / familiar. 자검 `_check_sidecar_disables_agent_file_terminal` |
| Qt in-process AIAgent merge | **CLOSED: NO-GO** (Phase1) | MainWindow에 AIAgent 금지. 자검 `_check_iris_agent_phase5_merge`, `_check_iris_agent_sidecar_only`, 통합 `_check_agent_merge_policy_closed` |
| ToolsetBoundary — api_server pin ≠ chat enable | **CLOSED** | platform `hermes-api-server`(+`computer_use`) pin은 gateway 호환; 채팅은 `_IRIS_DISABLED_TOOLSETS`로 `computer_use` 비활성. 자검 `_check_toolset_platform_chat_boundary` → `_check_agent_merge_policy_closed` |

구현으로 “합치기”를 다시 열지 않는다. 크래시 격리·REPLACE 정책을 코드 자검으로 고정한다.

## 8. 조치

1. Units 0–6 흡수 완료로 보고. 커밋/PR은 사용자 요청 시.
2. 잔재 표(위 5절) 중 브랜딩·fold 확장만 후속 백로그. Slot D·Qt-merge는 §7 CLOSED.
3. 구현 프롬프트는 `docs/prompts/completed/`로 이동.
