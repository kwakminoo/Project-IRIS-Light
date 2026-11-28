# FFC-06 제품 회귀 검증

기준은 2026-11-27의 격리 pytest 결과다. 139개 파일과 JUnit 1,483건 중 실패 요소 36건, skip 2건, 네이티브 중단 배치 4건을 확인했다. 아래 표의 번호는 원본 JUnit 실패 요소의 순서를 따른다. 5–19는 같은 테스트 ID의 세 글꼴 × 12/14/16/18/22px 조합이다. 원본은 `.tmp/wave17-final-independent-20261127/pytest-shards-final/results.json`에 있다.

| 원본 번호 | 파일·테스트 ID | 증상과 판정 | 현재 검사 |
| --- | --- | --- | --- |
| 1 | `test_chat_scroll::test_main_and_companion` · Main | 숨겨진 Qt 스크롤바 최대값 0 · 구 계약 | H1 DOM follow/hold와 페이드 PASS |
| 2 | 같은 ID · IDE | 숨겨진 Qt 스크롤바 최대값 0 · 구 계약 | 실제 IDE Companion의 host/view wheel PASS |
| 3 | 같은 ID · Email | 숨겨진 Qt 스크롤바 최대값 0 · 구 계약 | Email 패널 H1 DOM follow/hold와 페이드 PASS |
| 4 | 같은 ID · Calendar | 숨겨진 Qt 스크롤바 최대값 0 · 구 계약 | Calendar 패널 H1 DOM follow/hold와 페이드 PASS |
| 5–9 | `test_chat_typography::test_live_matrix` · 글꼴 1 | 숨겨진 로그 높이 0 · DOM 전환 후 제목/코드 고정 크기도 재현 | 동일한 5개 크기에서 본문·제목·코드 DOM PASS |
| 10–14 | 같은 ID · 글꼴 2 | 동일 계약 | 동일한 5개 크기 PASS |
| 15–19 | 같은 ID · 글꼴 3 | 동일 계약 | 동일한 5개 크기 PASS |
| 20 | `test_chat_typography::test_new_markdown_heading_size` | QTextDocument heading 누락 · 구 계약 | H1 heading의 실제 크기 PASS |
| 21 | `test_chat_typography::test_stream_positions_and_links_survive` | 숨은 HTML에 메시지 ID 없음 · 구 계약 | 실제 DOM의 스트림 텍스트·링크·메시지 ID PASS |
| 22 | `test_handoff_summary_worker::test_uses_the_resolved_upstream_model` | 이전 Hermes 클라이언트 mock에 응답 없음 · 구 계약 | 공용 Agent→API 경로에서 upstream 모델·URL·키 전달 PASS |
| 23 | `test_handoff_summary_worker::test_without_a_target_it_uses_the_plain_model_name` | 이전 mock에 모델 인자 없음 · 구 계약 | 직접 API 경로의 원래 모델명 PASS |
| 24 | `test_hermes_auth::test_force_rotate_replaces_strong` | 제거된 키 회전 인자 · 구 계약 | `test_env_step_has_no_legacy_force_rotate_api` PASS |
| 25 | `test_hermes_auth::test_weak_placeholder_is_rotated` | Desktop 초기화가 legacy 키를 보존 · 구 계약 | `test_legacy_gateway_placeholder_is_not_mutated` PASS |
| 26 | `test_hermes_auth::test_core_smoke_401_force_rotates` | Desktop smoke에서 legacy 키 회전을 기대 · 구 계약 | 401 진단 반환 및 Gateway 미변경 PASS |
| 27 | `test_hermes_auth::test_core_smoke_ready_fail_restarts` | Desktop smoke에서 legacy 재기동을 기대 · 구 계약 | 401/404 진단 반환 및 재기동 미호출 PASS |
| 28 | `test_ide_run_no_hang::test_bridge_exception_returns_clean_error_not_unboundlocalerror` | workspace-ready mock 누락 · 구 계약 | 실행 성공과 브리지 표시 실패를 함께 검증 PASS |
| 29 | `test_ide_run_no_hang::test_hung_bridge_call_times_out_instead_of_blocking_forever` | 이전 브리지 실행 메서드 mock · 구 계약 | 출력 미러 timeout과 Runtime 결과 PASS |
| 30 | `test_ide_run_no_hang::test_successful_run_reports_ok_and_output` | 이전 브리지 실행 메서드 mock · 구 계약 | 하나의 Runtime 실행과 Theia 출력 미러 PASS |
| 31 | `test_iris_owned_core_release::test_shipped_lock_identifies_owned_package` | Windows의 빈 Git 설정값 누락으로 128 · 환경 오염 | 명시 환경으로 자식 Git 전달 및 lock 계약 PASS |
| 32 | `test_model_selection_persistence::test_local_section_selects_runtime` | 원격 단일 모델의 이전 브랜드 묶음 계약 | 로컬/클라우드/단일 원격 분류와 선택 PASS |
| 33 | `test_past_chats::test_note_escapes_html` | 숨은 로그를 읽던 검사와 실제 노트의 HTML 해석 · 제품 결함 | H1 DOM에서 태그 원문 표시 PASS |
| 34 | `test_past_chats::test_note_has_no_play_link_and_is_not_read_aloud` | 숨은 로그를 읽던 검사 · 구 계약 | H1 DOM 노트 및 기존 답변에만 TTS 링크 PASS |
| 35 | `test_stt_ux::test_stt_pending_cancel_preserves_prior_messages` | 숨은 로그를 읽던 검사 · 구 계약 | H1 DOM의 기존 메시지 보존 및 대기 링크 제거 PASS |
| 36 | `test_stt_ux::test_stt_pending_completes_to_text` | 숨은 로그를 읽던 검사 · 구 계약 | H1 DOM의 실제 대기 링크와 인식 결과 교체 PASS |

## 이번 실행의 실패와 복구

- 초기 단일 pytest는 Windows `0xC0000409`로 중단됐다. 최소 조합에서는 Qt teardown의 `0xC0000005`도 확인했다. 세션 QApplication 선점, WebEngine bootstrap, 테스트 위젯 수명 및 deferred-delete 처리를 정리했다. 대화 전환 검사는 강제 종료 호출을 제거하고 창 파괴와 종료 코드 0을 직접 확인했다.
- 첫 완주에는 17개 실패가 기록됐다. gateway 진단 fixture가 남긴 Python 경로가 sidecar와 launcher를 오염시켰다. 진단에는 독립 환경 매핑을 넘기고, Windows 자식 Git에는 빈 설정값을 포함해 전달한다. 정적 Control 카탈로그 183개를 실행 레지스트리와 대조했다.
- NIP-12 재생에서 `python3.exe`를 거부하던 검사기를 실제 Python 런처 판정과 일치시켰다. 실행 항목 54/54는 한 건의 집중 재검을 포함한다. FPR-13 계약 17/17, 런처 파일 존재, 소스 매니페스트의 `legacy_migration_approved=false`를 따로 확인했다.
- 기존 승인 GUI 실패는 카드 링크를 찾기 전 timeout으로 기록돼 있다. 이번 Skip/Run 반복은 각 10/10, 각 회차 창 파괴와 정상 종료를 확인했다. 처음 관찰된 지연은 이번 반복에서 재현되지 않아 원인을 확정하지 않았다. 재사용·계획 변경 거부는 FPR-13 승인 ledger와 process 계약에서 검증했다.
- 종료 시 승인 대기 HTTP 요청이 즉시 반환되지 않는 실패를 추가로 재현했다. 종료 신호는 미결정 카드에 Skip을 전달하고, 이미 확정된 결정을 보존한다. 수정 후 새 프로세스 10회에서 Skip·Run·대기 중 종료가 모두 통과했다. 각 종료 응답은 `cancelled`였으며, 미승인 명령은 이전 실행의 표식 파일을 변경하지 않았다.
- 실제 GUI에서 첫 실행의 청크 카운트가 0이었다. stdout 큐에 청크가 있는 상태에서 UDP 완료 처리가 이를 생략하는 회귀 검사를 추가했다. 완료 fallback 전에 stdout 큐를 처리하게 수정했다. 이후 GUI 복구 시나리오에서 청크 12개, 최종 응답, 대화 복원, 창 파괴를 확인했다. `.tmp/ffc-06/gui-chat-closure/gui-chat.json`.
- 실제 Tesseract는 요청하지 않은 `chi_tra` 언어팩 경고를 출력하며 인식에 성공했다. 요청한 언어팩이 실패하면 계속 오류를 반환한다. 실제 스캔 PDF와 GUI OCR 종료에서 Tesseract 프로세스 및 첨부 워커 종료를 확인했다.
- Windows IDE 제품 검사는 Windows Store Python 실행 별칭에서 exit 9009를 재현했다. 작업공간 탐색이 Store 별칭과 앱·Core 인터프리터를 건너뛴 뒤 PATH의 다음 후보를 계속 검사하도록 수정했다. 제품 테스트 기준은 정상적인 IDE 파일 열기·쓰기·읽기와 동일한 Runtime 실행의 stdout 미러다.
- 제품 홈 재실행은 IDE 9/9 통과다. 실행 코드 0과 Theia 출력의 마지막 표식을 확인했다. `.tmp/ffc-06/product-home-recheck/logs/ide_product_control.log`.
- 스트리밍 중 첫 종료에서는 기존 강제 종료 경로가 사용됐다. 단일 sidecar stdin reader로 진행 중에도 Stop을 받게 하고, Owned Core 인터럽트가 끝날 시간을 준 다음 필요할 때만 기존 강제 종료 경로를 사용한다. 실제 스트리밍 재검은 sidecar 종료 코드 0과 강제 종료 로그 없음, Qt 워커 종료를 요구하며 통과했다. `.tmp/ffc-06/gui-stream-graceful/gui-chat.json`.
- 최신 FPR-13 혼합 실행은 23 PASS, 1 FAIL, 1 UNVERIFIED였다. 실패한 L3 셸에서는 승인과 명령 실행, stdout은 정상이고 모델 최종 응답 직전에 sidecar가 종료됐다. Windows stdin이 빈 값을 반환할 때 커널 파이프가 계속 열려 있는지 확인하도록 수정했다. 수정 후 L3 실제 셸 재검은 첫 회차에 승인·명령 실행·stdout·최종 모델 답변까지 통과했다. `.tmp/ffc-06/fpr13-release/results.json`, `.tmp/owned-live-shell/required/8814541aaa3c47fca08b27c9fd909792/evidence.json`.
- 실제 Memory GUI 최초 시도는 저장 호출 실패와 응답 길이 제한을 기록했다. 값과 도구 계약을 명시한 재실행에서 저장, 새 대화 회상, 갱신 및 설정 목록은 통과했다. 삭제 단계에서는 요청에 해당하는 모델 삭제 호출을 확인하지 못했다. 임시 Wiki는 보존됐다. `.tmp/ffc-06/gui-memory-recheck/gui-chat.json`.
- 추가 Memory 시도에서도 저장·회상·목록은 통과했다. 갱신과 삭제는 통과하지 못했다. 실제 GUI 혼합 도구 턴은 Native 파일 읽기 호출을 확인했지만, MCP 호출과 두 표식 반환은 실패했다. `.tmp/ffc-06/gui-memory-final/gui-chat.json`, `.tmp/ffc-06/gui-mcp-mixed/gui-chat.json`.
- 최종 혼합 GUI 재실행은 Native 파일 읽기와 승인된 MCP fixture 호출 모두 성공했다. 최종 응답은 두 값을 요청 순서로 표시했으나 ASCII 하이픈(U+002D)을 줄바꿈 금지 하이픈(U+2011)으로 바꿨다. 정확한 문자열 계약은 FAIL이다. `.tmp/ffc-06/gui-mcp-verified/gui-chat.json` 및 해당 프로필의 `engine.log`.
- Windows 파이프 수정 후 모델 생성 중 종료를 다시 검증했다. 모델 청크 수신 후 앱과 sidecar가 종료 코드 0으로 끝났고, 실행 로그로 추적한 sidecar PID 6개가 남지 않았다. `.tmp/ffc-06/gui-stream-verified/gui-chat.json`.
