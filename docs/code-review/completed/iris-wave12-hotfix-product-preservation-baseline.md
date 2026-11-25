# IRIS Wave 1.2 Hotfix — Product Preservation Baseline

| 항목 | 내용 |
|---|---|
| 문서 번호 | W12-HF-00 |
| 작성일 | 2026-11-25 |
| 관련 | Wave 1.2 Hotfix & Validation |
| 대상 | HEAD `d23f937` 제품 표면 기준선 |
| 목적 | Hotfix 전 기능·UI 보존 기준 고정 |

## 1. 결론

기준 HEAD는 `d23f937`이다. Wave 1.2(`94bfa33`) 이후 모델 즐겨찾기·피커 abort·스크롤바 투명은 후속 커밋으로 코드상 복구됐다. Trusted Context·승인·Shell Box는 골격만 닫혔고 turn freeze·전역 confirm·FIFO·cancel 타이밍은 PARTIAL/OPEN이다. Actual GUI·Actual Agent Turn은 이 문서 작성 시점 Unverified다.

## 2. 기준 커밋

| 커밋 | 역할 |
|---|---|
| `d23f937` | HEAD — duplicate `model_favorite_toggled` 제거 |
| `b7b87f6` | 착지 paint + 모델 즐겨찾기 UI/API 복구 |
| `b98bcd0` | favorites 테스트를 당시 축소 API에 맞춤 (중간 회귀 구간) |
| `72aad89` | 피커 TypeError 종료 차단 (favorites 인자 제거 방식) |
| `18902c5` | H1 transcript 스크롤바 투명 |
| `94bfa33` | Wave 1.2 trusted context / H1 shell / IDE stream / patch sync |
| `808b313` | Wave 1.1 |

## 3. 기능 목록

상태: Verified = 헤드리스 계약 통과. Existing but Unverified = 코드 존재·라이브 GUI/턴 미확인. Regression Detected = 조사상 결함. Missing = 경로 없음. N/A = 이번 범위 밖.

| 기능 | 상태 | 호출/표시 경로 | 비고 |
|---|---|---|---|
| Home HUD | Existing but Unverified | MainWindow + ChatPanel | 레이아웃 보존 대상 |
| Chat / H1 Transcript | Existing but Unverified | `transcript_h1` + ChatPanel | follow-tail 미배선(Regression Detected) |
| 모델 선택창 | Existing but Unverified | `ModelPickerMenu` / `ModelBrandDialog` | 코드 FIXED (`b7b87f6`) |
| 모델 즐겨찾기 | Existing but Unverified | ★ → `model_favorite_prefs` / DB `model_favorites_v1` | 코드 FIXED |
| Provider 그룹·검색·필터 | Existing but Unverified | `split_picker_groups` | |
| 로컬/외부 모델 연결 | Existing but Unverified | provider roster | |
| 스트리밍 응답 | Existing but Unverified | sidecar → H1 | |
| 모델 변경·선택 저장 | Existing but Unverified | ChatPanel + prefs | |
| Chat History | Existing but Unverified | DB conversations | |
| Writing Card | Existing but Unverified | run_visibility | |
| Code Block | Existing but Unverified | H1 render | |
| App Host | Existing but Unverified | apps control | |
| Shell Box | Existing but Unverified | H1 ToolShellPart + shell_controller | 신규 UI 금지 |
| 승인 모드 UI | Existing but Unverified | Ask / Allowlist / Run Everything | HUD 재도입 금지 |
| Live Activity Panel | Existing but Unverified | 모니터 전용 | |
| IDE Companion | Existing but Unverified | 80:20 tile | |
| Theia Terminal | Regression Detected | `appendTerminalOutput` + `sendText` 폴백 | HF-08 |
| 파일 열기/저장/수정 | Existing but Unverified | IDE + patch | |
| Wiki / 이메일 / 캘린더 | Existing but Unverified | control actions | |
| Browser / Web Search | Existing but Unverified | browser tools | |
| Voice | Existing but Unverified | | |
| Android Emulator | Existing but Unverified | | |
| Aloha / Routine | Existing but Unverified | | |
| 사용자 설정 | Existing but Unverified | `~/.iris-light` | 초기화 금지 |
| 시작·설치 프로토콜 | Existing but Unverified | engine install | |
| Trusted Execution Context | Regression Detected | live window bind | HF-03 |
| Request Approval Ledger | Regression Detected | `rt.set_human_confirm` 잔존 | HF-04 |
| Shell gate wait/FIFO | Regression Detected | unbounded wait + FIFO | HF-05 |
| Shell lifecycle cancel | Regression Detected | late `bind_run` | HF-06 |
| Shell output memory | Regression Detected | unbounded `parts` | HF-07 |
| Workspace env (product) | Existing but Unverified | Resolver + `build_child_env` | HF-09 audit |
| Patch buffer conflicts | Regression Detected | probe fail → `[]` | HF-10 |
| Agent engine probe | Verified (contract) | `None` = ready | 라이브 hermes-agent OK |
| Actual Agent Turn | Existing but Unverified | sidecar + land | HF-11 |

## 4. UI 기준선 (보호 항목)

| 항목 | 기준 | 현재 |
|---|---|---|
| 레이아웃·토큰·여백 | Wave 1.2 이전 Home/IDE | 전면 리디자인 금지 |
| 모델 선택창·★ | `b7b87f6` 복구본 | Actual GUI 대기 |
| Shell Box 디자인 | H1 카드 | 신규 패널 금지 |
| 승인 모드 하단 UI | 기존 3모드 | 유지 |
| 스크롤바 투명·단일 | `18902c5` + `_log.hide()` | CSS Verified 가능 / 육안 Unverified |
| 스크롤 위치·follow-tail | 하단 follow, 상단 hold | H1 DOM 미연결 → HF-02 |
| 깜빡임 방지 | 부분 갱신 | 유지 |

## 5. 구조

```text
User → MainWindow / ChatPanel / IDE Companion
  ├─ ModelPicker → favorites DB
  ├─ H1 Transcript (visible scroll)
  ├─ Shell Box (H1 tool block)
  └─ Control invoke
       ├─ strip_trust_fields
       ├─ ExecutionContext (should be turn-frozen)
       ├─ RequestApprovalLedger
       ├─ shell_controller (request↔block↔run)
       └─ ExecutionRuntime / Theia mirror / patch
```

## 6. 조치

1. HF-01~02: GUI 검증·follow-tail 재배선.
2. HF-03~10: 조사된 Regression만 최소 수정.
3. HF-11~12: Agent Turn 증거 + 보존 게이트 보고서 후 `main` push.

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Wave 1.2 shell_controller / ledger | 요청 수명주기 | 이미 있음 — 잔여만 고침 |
| verify-iris | GUI/control proof | agent-turn feature는 선택 |
| Hermes pin/overlay | — | Ownership 후속 작업 |
