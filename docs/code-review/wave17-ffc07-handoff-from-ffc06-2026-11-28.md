# FFC-06 → FFC-07 인수인계

2026-11-28 기준. 원본 36개 실패의 대응표와 재실행 증거는 [FFC-06 회귀 기록](wave17-ffc06-product-regression-2026-11-28.md)에 있다. 제품·배포 판정은 [공통 추적표](wave17-ffc-tracker.md)의 FFC-06 상태를 따른다.

## 회귀 기준

- Windows용 first-party 기준은 `python -m pytest tests`다. native exit 및 JUnit 미생성을 별도 실패로 보존한다. 환경에 따른 skip은 CLI 출력과 JUnit에 기록한다.
- Transcript 기준은 H1 WebEngine이다. `test_chat_scroll`, `test_chat_typography`, `_check_transcript_scroll`, `_check_h1_wheel_hit`, `_check_transcript_no_blank_flash`를 유지한다.
- Process 승인은 `python -m iris.ui._check_fpr_product_gui process`에서 실제 카드 및 종료 취소를 확인한다. 승인 재사용과 계획 변경은 `_check_request_approval`, `_check_process_manage`를 함께 실행한다.
- 변경한 Qt 대화 전환 검사는 `python -m iris.ui._check_conversation_switch_cancel`의 정상 종료 코드로 평가한다. Worker나 Chromium 강제 종료를 정상 종료 증거로 집계하지 않는다.

## 실증이 더 필요한 경로

- 실제 GUI 모델의 청크 전달, 최종 응답, 대화 복원, 생성 중 정상 종료는 증거가 있다. 같은 턴에서 중간 DOM 프레임을 별도로 샘플링하는 검사는 추가로 필요하다.
- 실제 GUI의 Memory 삭제, Todo/Clarify는 계약 테스트와 별도로 판정한다. 진행 중인 IDE·Wiki·Voice 종료를 독립 프로필에서 실행하고 잔류 프로세스를 확인한다. OCR 종료, IDE 시나리오 완료 후 정상 종료는 확인했다.
- 마지막 실제 GUI 혼합 턴에서는 Native 파일 읽기와 MCP 호출이 모두 성공했다. 모델이 두 표식을 반환하면서 ASCII 하이픈을 U+2011로 바꿨으므로 정확 일치 검사는 실패로 유지한다. 다중 MCP 재연결 계약은 통과했다.
- 실기기 마이크·스피커 및 선택 TTS 모델 검증에는 장치와 설치된 런타임이 필요하다.
