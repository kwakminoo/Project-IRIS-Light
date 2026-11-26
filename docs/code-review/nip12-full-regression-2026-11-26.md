# NIP-12 Full Regression (Wave 1.6)

| 항목 | 내용 |
|---|---|
| 문서 번호 | NIP12-REG-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Wave 1.6 · FPR13 contracts · verify-iris `_check_*` |
| 대상 | `main` @ `029c1ce` + dirty local fixes |
| 목적 | 핵심 영역 전체 회귀 실측·결함 최소 수정·증거 고정 |

## 1. 결론

NIP-12 계약 회귀는 **PASS (57/57)**. HEAD `029c1ceef289d78f7fb4a66271d686c95cd20aba`, `legacy_migration_approved=false` 유지.  
1차 실행에서 6건 FAIL → 원인 분류 후 최소 수정·모듈 경로 정정 → 재실행 전원 green.  
Wave 2(NIP-13)는 개발 CONDITIONAL GO / 공개 NO-GO (NIP-09 PARTIAL · FPR13 L4 `ide_product_control` UNVERIFIED). FPR13 l04는 후속 live에서 PASS.

증거: `.tmp/nip12-regression/results.json`, `.tmp/nip12-regression/STATUS.md`.

## 2. PASS/FAIL matrix

| Area | Status | Commands (entry) |
|---|---|---|
| Engine | PASS | `-m iris.engine._check_*` · `agent_runtime` · uv probe boost |
| Native Tool | PASS | tool_contract · native_tool_* · absorbed_tool_* · speak_surface · agent_turn_tools |
| Approval Policy | PASS | request_approval · **ui.chat._check_run_approval** · execution_policy · process_manage · shell_gate |
| Execution Runtime | PASS | execution_runtime · execution_context · workspace_environment · file_patch · run_env |
| IDE Bridge | PASS | iris_ide_window · companion_tile · file_drop · control_http · ide_tiler |
| GUI contracts | PASS | chat_landing · sidecar_done · gui_singleton · calendar · turn_followup |
| Memory/Session/Context | PASS | history_handoff · conversation_switch_cancel · chat_ownership |
| Provider | PASS | provider_resolve · model_roster · api_providers · model_picker_roster |
| Install/Update/Recovery | PASS | uv_probe · hermes_update · **app_update** · gateway_legacy_isolated · transcript_notices |
| Standard Suite | PASS | `_check_fpr13_runner --contracts-only` |
| Unit/Integration | PASS | no_console · hermes_install_bypass · setup_repair · engine_types · request_model · part_contract |
| Launcher | PASS | `scripts/build_iris_exe.ps1` · `dist/IRIS.exe` · Desktop lnk → thin launcher |
| KEEP | PASS | `legacy_migration_approved=false` |

## 3. 구조

```
NIP-12 runner (local)
  ├─ Area packs → .venv\Scripts\python.exe -m iris…/_check_*
  ├─ FPR13 --contracts-only → 17 contract scenarios
  ├─ unittest selected suite
  ├─ thin launcher build / presence
  └─ KEEP read SOURCE_MANIFEST.json
        │
        ▼
  .tmp/nip12-regression/{STATUS.md, results.json, logs/*}
```

요청이 갈라지는 지점:

- **계약 자검** (이번 PASS 범위) vs **live/GUI/lifecycle flag** (NIP-08/09/10 잔여).
- **Title/summary side-call**: 예전 `_hermes`/gateway → 현재 `collect_reply` agent→API remap.
- **Update notice**: ghost `_log` HTML → H1 `ChatNotice` transcript.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 막지 못한 이유 / 조치 |
|---|---|---|
| `iris.ui._check_app_update` | `_log.toHtml()`에 `iris-update://` 기대 | H1 notice로 이미 이동. 자검을 H1 blob + QApp 선행으로 맞춤. |
| `tests.test_request_model` SideCall | `_hermes` import | gateway-free `backend_call`에서 심볼 삭제됨. `collect_reply`+API remap으로 계약 유지. |
| `tests.test_setup_hermes_runtime_repair` | hermes 폴더만 두고 gate 기대 | gate는 `active=hermes-agent` selection + cutover OFF일 때만. fixture 보강. |
| `iris.ui._check_conversation_switch_cancel` | 어설트 ok 후 exit≠0 | MainWindow/WebEngine 종료 ACCESS_VIOLATION. harness `os._exit(0)`. |
| 매핑 `iris.system._check_run_approval` | Module not found | 실제 모듈은 `iris.ui.chat._check_run_approval`. |
| `iris.ui.window._check_file_drop` OLE | 1차 effect=0 | 포커스/커서 레이스 추정. 단독·최종 재실행 PASS. |
| `backend_call.collect_reply` | agent→API | 게이트웨이 쓰기 없음 (의도). |
| `install_iris_agent_with_system_python` gate | reference 교체 차단 | `legacy_migration_approved` false 유지. |

### 하지 않은 일

- `legacy_migration_approved` 승격
- commit / push
- hermes 물리 삭제
- FPR13 `--include-live` / `--include-gui` / `--include-lifecycle` 전수
- NIP-09 외부 모델 live 매트릭스

## 5. 개선안

| 빈 자리 | 제안 |
|---|---|
| OLE drop 간헐 effect=0 | file_drop 체크에 재시도·커서 hit 실패 시 soft-skip 대신 원인 로그를 results에 고정 |
| WebEngine 체크 teardown | conversation_switch뿐 아니라 MainWindow 보유 `_check_*`에 공통 종료 헬퍼 |
| 영역 매핑 단일 소스 | NIP-12 area→module 표를 코드(러너)로 고정해 잘못된 `-m` 경로 재발 방지 |
| live/GUI 묶음 | NIP-12 contracts PASS 이후 NIP-08 flag 실실행을 별도 STATUS로 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| FPR13 runner (`_check_fpr13_runner`) | contracts-only 시나리오 목록·로그 디렉터리 | 이미 사용. live/gui 플래그는 범위 밖 |
| verify-iris `prove_feature.py` | feature→module 매핑·evidence 폴더 | 영역 전수는 `_check_*` 직접 호출이 더 넓음 |
| pytest-xdist / 대형 CI matrix | 병렬 회귀 | Windows OLE/Qt HWND 체크는 병렬 시 레이스. 직렬 유지 |
| Qt `QWebEngine` shutdown guides | 프로세스 강제 종료 패턴 | harness에만 `os._exit`; 제품 경로에 넣지 않음 |

찾지 못함: NIP-12 전용 기존 러너 문서 (신규 작성).

## 7. Wave 2 함의

NIP-12 contracts green만으로 공개 GO가 되지 않는다. NIP-09 PARTIAL과 FPR13 잔여(FAIL/UNVERIFIED)가 공개 진입을 막는다.

## 8. 조치

1. 계약 회귀 증거는 PASS로 고정. Wave 2 공개·migration 승격은 하지 않는다.
2. 다음 가역 단위: FPR13 l04 재번, L4 `--product-home`, NIP-09 auto tool 매트릭스.
3. 커밋·push는 사용자 요청 시에만.
