# Wave 1.7 Final Residual Closure

## 세션 재개 상태 (2026-11-27 토큰 끊김 이후)

| 단위 | 상태 | 증거 |
|---|---|---|
| FRC-01A/B | **COMPLETE** | unittest + `.tmp/frc/post-cutoff-mcp` 2/2 + `.tmp/frc/post-cutoff-native` 2/2. 혼합(`mixed`) 1회는 FAIL — `local.search_files` 스코프 밖 경로·MCP만 회수(`.tmp/frc/post-cutoff-mixed`). 단독 MCP/Native PASS와 분리 |
| FRC-02 | **PARTIAL** | 15행 인벤토리 + `skills_list`/`skill_view`/`vision_analyze` 흡수 |
| FRC-03 | **PARTIAL** | `TurnTodoStore` + `_check_turn_todo_evidence` |
| FRC-06 | **PARTIAL** | `_check_frc06_panel_land` + `_log` skip 행렬 |
| FRC-05 | **PARTIAL** | 파일명→attachment_id 유일 해석 + `_check_pdf_page_range` disambiguation. [진행](wave17-frc05-progress-2026-11-27.md) |
| FRC-07 | **PARTIAL** | 분류 문서 + `apply_env_to_hermes.ps1` 퇴역 + `_check_gateway_legacy_isolated` |
| FRC-04A | **OPEN** | 서명 Webhook·Connector 미구현 |
| FRC-04B | **PARTIAL** | 승인 직후 schema fingerprint 거부 자검 |
| FRC-08 | **PARTIAL** | 격리 L6 + Setup 0.1.18 + contracts-only 17 PASS. [검증 상태](wave17-frc08-verify-status-2026-11-27.md) |
| FRC-08W | **BLOCKED** | 두 번째 클린 Windows OS 없음. 가용성 제약 명시 |
| Wave 2 | **NO-GO** | `legacy_migration_approved` 유지 false. 커밋·push 없음 |

기준선은 `main`의 `619f876d06fcf51ea0ea03e8148d30feb1c0e3a1`이며 작업 시작 시 Git 작업 트리는 깨끗했다. 앱 Python 3.13.7로 제품 슬롯을 조회했다. 활성 `iris-agent.slot-272facc0f5fd4b6f`에서 Core `0.1.2+iris.a382af23`, Python 3.14.7, MCP SDK 2.3.0을 확인했다. Runtime probe를 통과했고, Vendor와 활성 슬롯의 `SOURCE_MANIFEST.json`, `uv.lock`, `run_agent.py` 해시가 일치했다. 이전 슬롯은 `iris-agent.slot-e38f3ea761714c36`이다. Core import 중 선택적 `plugins.web` 경고가 한 번 출력됐다.

## 잔여 추적표

| ID · 분류 · 심각도 | 출처 및 현재 구현 | 결함 및 원인 | 필요한 변경 · 의존성 | 완료 기준 및 검증 |
|---|---|---|---|---|
| FRC-01A · FIX · P0 · **COMPLETE** | NIP-09 및 독립 검증. Sidecar → `openai_context_budget` → `assemble_iris_model_tools(..., user_message=)` | 고정 64K 전달 제거. 로컬 `/v1`에서 maximum/loaded/budget/tools 보고 후 압축기·툴 표면 반영. ≤8192면 compact system prompt | — | 계약: `python -m unittest tests.test_wave17_adaptive_context -v` OK. 실모델: `.tmp/frc/post-cutoff-mcp` MCP 2/2 PASS (`CONTEXT_BUDGET`·고유 마커). compact 재현 `.tmp/frc/compact-mcp`·`compact-native` PASS. 이전 adaptive FAIL은 host `No module named 'PyQt6'` |
| FRC-01B · IMPLEMENT / VERIFY · P0 · **COMPLETE** | `OllamaClient.openai_context_budget`, tool_surface compact 예산, sidecar 로그 | 진단 연결 구현. 기본 budget=4096(또는 model `num_ctx`), tools capability 반영 | — | 동일 unittest + MCP 실측. Native `.tmp/frc/post-cutoff-native` 2/2 PASS (검색→읽기→마커) |
| FRC-02 · IMPLEMENT / VERIFY · P1 | 기능 흡수표. Native 스킬, 첨부 Vision, Voice, Wiki, Routine, IDE·Browser, MCP. [바인딩 인벤토리](wave17-frc02-binding-inventory-2026-11-27.md) | 이미지 생성·TTS·일정·연결 등 모델 바인딩 잔여. 실제 Vision·스킬 실행 증거 부족 | 기존 실행 정본에 Native 액션을 연결하고 15개 진입점 검증. 외부 제공자 상태 별도 기록. **부분:** `skills_list`/`skill_view`/`vision_analyze` 흡수(home_n=119). `session_search`는 FRC-01 eager 핀으로 보류 | 바인딩부터 정책과 실제 실행까지 기능별 검증. 인벤토리 15행 + aliases/wire/contract/hermes_disabled/binding 자검 통과(2026-11-27) |
| FRC-03 · IMPLEMENT · P1 · **PARTIAL** | R-ASSETS-ABSORB, Wave 2 U08/U09. Owned Loop, Turn Context, Engine fork. [진행](wave17-frc03-progress-2026-11-27.md) | **닫힘:** 세션 스코프 `TurnTodoStore` — `completed`는 비어 있지 않은 `TodoEvidence` 필수 (`iris/runtime/turn_todo.py`). **잔여:** 기억 CRUD, clarify 대기/재개, delegate 권한·수명주기, todo Speak 배선, 턴 영속화 | FRC-01 이후 세션·턴 스코프 상태와 실행 정본에 연결. 다음 단위는 clarify 또는 memory | 자검: `python -m iris.runtime._check_turn_todo_evidence`. 전체 완료 시 사용자 재개·세션 기억·하위 취소 실모델 검증 |
| FRC-04A · IMPLEMENT · P1 | FC Gateway/MCP 계약. 토큰, 주체별 SQLite, 승인, 세 프로토콜 | 서명 Webhook 및 공용 Connector 진입점 미구현 | 인증·재생 방지·중복·한도 및 채널 소유 매핑을 기존 Gateway 위에 추가 | 루프백에서 유효 이벤트 실행, 위조·중복·재생·잘못된 소유권 거부 |
| FRC-04B · FIX / VERIFY · P1 · **PARTIAL** | 호스트 MCP 바인딩, 구성/스키마 지문, 승인. [진행](wave17-frc04b-progress-2026-11-27.md) | **닫힘(단위):** 승인 직후 스키마 지문 불일치 → `schema_changed` 거부 (`_check_schema_refuse_after_approval`). **잔여:** dual-server isolation, stdio kill 재연결, 거부·취소·재시작·단절 조합, 실모델 MCP | 다음 단위는 dual-server discovery isolation 또는 stdio reconnect | 자검: `python -m iris.mcp._check_schema_refuse_after_approval`. 전체 완료 시 다중 서버·실모델·단절 조합 |
| FRC-05 · FIX / IMPLEMENT · P1 · **PARTIAL** | FC 문서 계약. 대화 첨부 ID, PDF 범위, 구조화 OCR. [진행](wave17-frc05-progress-2026-11-27.md) | **닫힘:** 유일 basename → canonicalize_attachment_ref / 중복은 ambiguous+후보 id. **잔여:** 추출 캐시(OCR 재처리), OCR 취소 자검, 201쪽 실모델 | 접근 확인 후 공용 추출 캐시 · OCR 취소 검증 · 권한·원본 변경 | python -m iris.ui._check_pdf_page_range (disambiguation 포함). 전체 완료 시 201쪽 실모델·캐시·취소 |
| FRC-06 · FIX / MIGRATE · P1 · **부분** | FIG·FPR13·NIP-12·ACF. WebEngine H1. [레거시 테스트 행렬](wave17-frc06-legacy-test-matrix-2026-11-27.md) | `_log` scroll/typography unittest는 숨김 QTextEdit·Qt abort. 승인 카드·IDE·Picker·Voice 잔여 | **이번:** `_check_frc06_panel_land` + `_log` 케이스 skip. 휠/페이드/live CSS inject·승인·IDE는 다음 단위 | `python -m iris.ui.chat._check_frc06_panel_land`. 기존 `_check_transcript_scroll` / `_check_transcript_h1` / `_check_transcript_no_blank_flash` |
| FRC-07 · MIGRATE / RETIRE · P1 · **PARTIAL** | FC 호환 표, FIG-29, Native 전환 검사. [분류](wave17-frc07-legacy-classification-2026-11-27.md) | **닫힘:** 잔여 핫패스 분류표 + `scripts/apply_env_to_hermes.ps1` 퇴역(대체 `.env.example`/migrate). **잔여:** hermes-plugins 패키징, gateway 진단 모듈 분리, absorbed_toolsets bake, cli_shim | hermes 물리 삭제·`legacy_migration_approved` 금지. 다음 후보는 문서/패키징 감사 후 | `python -m iris.system._check_gateway_legacy_isolated`. 전체 완료 시 패키징·진단 분리 증거 |
| FRC-08 · VERIFY · P1 · **PARTIAL** | Wave 2 U07–U11, FPR13 설치 검사와 기존 빌드. [검증 상태](wave17-frc08-verify-status-2026-11-27.md) | **닫힘(이 PC):** 격리 Core 수명주기 PASS · Launcher/Setup 0.1.18 재빌드(SHA 일치) · 2026-11-27 `--contracts-only` 17 PASS. **잔여:** 임시 확장 공개 경계 실측 · L3/L4/L5 live·GUI(선택) | 공개 migration·`legacy_migration_approved` 승격 금지. L6 재실행 기본 불필요 | 증거: `.tmp/wave17-functional-closure/fpr13-isolated-final/results.json` (18P/0F, `installer_lifecycle` PASS) · `.tmp/w17-fc-build/dist/IRIS-Setup-0.1.18.exe` · `.tmp/wave17-functional-closure/fpr13-contracts-frc08-verify/results.json` |
| FRC-08W · VERIFY · P1 · **BLOCKED** | 독립 검증의 Windows Setup. [검증 상태](wave17-frc08-verify-status-2026-11-27.md) | **가용성 제약:** 이 머신은 Windows 11 Home 단일 OS. 두 번째 클린 Windows·준비된 Hyper-V VM(`Get-VM` 불가) 없음. 클린 OS Setup 설치·업데이트·롤백 증거 없음 | 별도 클린 Windows 또는 관리 가능 VM이 생길 때까지 보류. 격리 디렉터리 L6는 FRC-08 증거로만 인정 | OS 격리 검증 **또는** 가용성 제약을 명시 ← **이번: 제약 명시 완료** |

근거는 [Wave 1.6 추적표](wave16-implementation-tracker-2026-11-26.md), [NIP-09](nip09-model-quality-closure-2026-11-26.md), [NIP-12](nip12-full-regression-2026-11-26.md), [Wave 1.7 추적표](wave17-implementation-tracker-2026-11-26.md), [Wave 1.7 독립 검증](wave17-independent-validation-2026-11-26.md), [FC 추적표](wave17-fc-tracker-2026-11-27.md), [흡수표](wave17-fc-functional-absorption.md), [Gateway/MCP 계약](wave17-fc-gateway-mcp-contract.md), [문서 계약](wave17-fc-document-intelligence-contract.md), [호환 이전](wave17-fc-compatibility-migration.md), [FC 인수인계](wave17-fc-validation-handoff.md), [최종 독립 결과](wave17-final-independent-2026-11-27.md), [R-ASSETS-ABSORB](phase00-residual-work-tracker-2026-11-26.md), [FIG-29](fig-29-hermes-residual-dependency-audit-2026-11-26.md), [FPR13 실측](phase25-fpr13-live-2026-11-26.md), [ACF GUI 결과](gpt-oss-20b-acf-gui-test-종합-2026-11-26.md), [Wave 2 U07–U11 상세 브리프](iris-agent-unified-runtime-wave2-brief.md)에 있다.
