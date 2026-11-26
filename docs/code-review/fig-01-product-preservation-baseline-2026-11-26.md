# FIG-01 Product Preservation Baseline

| 항목 | 내용 |
|---|---|
| 문서 번호 | FIG-01 |
| 작성일 | 2026-11-26 |
| 관련 | FIG-00 · FPR-00 · FPR-14 · FGC |
| 대상 | IRIS 제품 표면 보존 |
| 목적 | 정상 UI를 불필요 수정하지 않기 위한 상태표 |

## 1. 결론

대부분 표면은 **EXISTING BUT UNVERIFIED**(이번 세션 GUI 전수 미촬영). Shell Box·Native routing·Process Control은 기존 증거로 VERIFIED에 가깝다. 모델 shell 성공 왕복·Code Box 라이브·즐겨찾기 라이브·통합 승인 HUD 잔여는 REGRESSION 또는 UNVERIFIED로 남긴다. 문제 없는 UI는 손대지 않는다.

## 2. 보존 표

| 항목 | 상태 | 근거 |
|---|---|---|
| Home | EXISTING BUT UNVERIFIED | GUI 기동 중; 화면 미촬영 |
| IDE Companion | EXISTING BUT UNVERIFIED | 계약 코드 존재; 라이브 미검 |
| H1 Transcript | EXISTING BUT UNVERIFIED | `_check_transcript_*` 과거 pass |
| 모델 선택창 | EXISTING BUT UNVERIFIED | FPR-14 roster/open ok 주장 |
| 모델 검색 | EXISTING BUT UNVERIFIED | — |
| 즐겨찾기 추가/해제/순서/복원 | UNVERIFIED | FPR-14 IDE·즐겨찾기 라이브 미검 |
| Provider 설정 | EXISTING BUT UNVERIFIED | config.yaml custom |
| 실제 모델 변경 | UNVERIFIED | — |
| 스트리밍 | EXISTING BUT UNVERIFIED | — |
| Shell Box | VERIFIED (Control) / UNVERIFIED (모델 경로) | FPR-01 Control+스크린샷; 모델 exit 1 |
| Code Box | UNVERIFIED | 120B TEST08 코드 생성만; GUI 미검 |
| App Host | EXISTING BUT UNVERIFIED | part_contract 과거 ok |
| Writing Card | EXISTING BUT UNVERIFIED | — |
| Live Activity Panel | EXISTING BUT UNVERIFIED | FPR Home+Live 기동 기록 |
| 하단 승인 모드 | EXISTING BUT UNVERIFIED | Ask/Allowlist/Everything 코드 유지 |
| 스크롤바 디자인 | EXISTING BUT UNVERIFIED | `_check_transcript_h1` 과거 |
| Wiki | UNVERIFIED | 120B OpenRouter 성공 주장; 재현 미 |
| Browser | VERIFIED (별칭 후 모델 open+url) / 부분 | 20B retest ok:true; needs_reapproval·지연 잔여 |
| Web Search | EXISTING BUT UNVERIFIED | — |
| Email Compose Draft | UNVERIFIED / 부분 실패 | 20B compose dialog not opened; 120B 도구 미호출 |
| Calendar | EXISTING BUT UNVERIFIED | — |
| Voice | EXISTING BUT UNVERIFIED | — |
| Emulator | EXISTING BUT UNVERIFIED | — |
| Aloha | EXISTING BUT UNVERIFIED | — |
| Routine | EXISTING BUT UNVERIFIED | — |
| 사용자 설정·대화 기록 | VERIFIED 보존 원칙 | 이번 작업 삭제/초기화 없음 |

## 3. 조치

1. GUI 손대는 수정은 회귀 증거가 있는 표면만.
2. Gate D에서 UNVERIFIED → VERIFIED/REGRESSION으로 승격.
