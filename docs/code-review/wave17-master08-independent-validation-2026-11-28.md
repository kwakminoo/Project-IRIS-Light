# Wave 1.7 MASTER 08 독립 최종 검증

| 항목 | 결과 |
| --- | --- |
| 판정 | **NO-GO** |
| 시작 HEAD | `434081fd161f3b011d1897cc5791ccf7100de9c6` |
| 시작 작업 트리 지문 | `5717572f990c61be6cd6add32e537ac1a82b72be468d533dab92a403f04ad9a5` (4,140 files) |
| 최종 작업 트리 지문 | `b15f5ef9050b383e715a15299b820be6c567a9ccee4f29f41d0407a2814c3f9d` (4,140 files) |
| 활성 슬롯 | `iris-agent.slot-272facc0f5fd4b6f` |
| 실제 모델 | `gpt-oss:20b` · Ollama 0.40.15 |
| 제품 Python / Owned Python | 3.13.7 / 3.14.7 (수명주기 증거) |
| Context | advertised 131,072 · 요청 64,000 · 실제 응답 관측 loaded 4,096 |
| 보안 위반 | 실측 0 |

## 결론

Headless 실제 모델 품질, Memory, Gateway, 201페이지 문서, 전체 pytest, Process 승인, 격리 수명주기는 기준을 충족했다. 그러나 제품 GUI의 Native/MCP 혼합 도구 작업은 두 번 모두 전체 기준에 실패했다. 첫 실행은 단독 Native 무호출과 Shell 미실행 가짜 성공, 재시도는 Native 검색 생략과 mixed grounding 실패였다. 실제 제품 GUI 안정성은 Wave 2 기반 P1이므로 CONDITIONAL GO가 아니다.

Wave 2 U07–U11 신규 기능, 원격 push, release, 공개 migration은 수행하지 않았다. 클린 Windows, 코드 서명, 외부 계정/OAuth는 별도 Gate다.

## 15 Gate

| Gate | 판정 | 독립 재현 근거 |
| --- | --- | --- |
| 01 제품 실행 | **PARTIAL** | 제품 일반 채팅·스트리밍·대화 복원·모델 일치 PASS. 물리 모델 삭제 후 앱 재시작 및 Provider별 vision/streaming 거절 실측은 미실행. |
| 02 Runtime 독립성 | **PASS** | Gateway HTTP disabled인 Desktop에서 InternalSidecar 실제 모델·Memory·GUI 실행. `product_ready_no_gateway`, `product_no_gateway_spawn`, legacy isolation PASS. |
| 03 Memory | **PASS** | GUI 저장→새 대화 회수→갱신→설정 목록→삭제→삭제 후 비회수 6단계 PASS. 주체/범위/충돌/재시작/비밀 거절 L2 PASS. |
| 04 Wiki 분리 | **PASS** | Memory 전 과정에서 Wiki fixture SHA-256 불변. Wiki/Browser GUI 및 PDF 경로 회귀 PASS. |
| 05 기능 흡수 | **PARTIAL** | 15개 canonical binding 및 정책 계약은 PASS. 실제 모델 Todo/Clarify/Delegation, Voice/TTS/image/computer use의 제품 전 과정은 미완. |
| 06 기본 Agent Intelligence | **PARTIAL** | Todo host evidence, Clarify wait/resume, Delegate 상한·취소 계약 PASS; Memory L4/L5 PASS. Todo/Clarify/Delegate L4/L5 미실행. |
| 07 Gateway | **PASS** | auth/run/SSE/approval/MCP/final/ownership/restart/search와 webhook 위조·만료·중복 거절 PASS. 외부 플랫폼 push는 범위 밖 UNVERIFIED. |
| 08 MCP | **PARTIAL** | 실제 stdio, 멀티 서버 재연결, schema drift 거절, timeout, Gateway 및 GUI 승인 PASS. HTTP/SSE transport와 실제 사람 denial GUI는 이번 독립 실행에서 미재현. |
| 09 Document | **PARTIAL** | 201p 실제 모델이 87쪽만 읽고 정확 표식 회수; cache/cancel/error 계약과 attachment pytest PASS. 한글/영문 실제 OCR 전체 매트릭스는 이번 실행에서 L4 재현하지 않음. |
| 10 복합 품질 | **PASS (headless)** | Native 10/10, MCP 10/10, mixed 10/10; 성공 grounding 100%, 권한 위반 0. 일부 회차는 제한 인수 복구가 필요했다. |
| 11 GUI 안정성 | **FAIL** | 제품 도구 묶음 0/2 전체 성공. Process 승인 10/10, Memory 7/7, 스트리밍 종료, IDE 9/9는 PASS. |
| 12 호환성 | **PASS** | 전체 pytest 1,299 PASS + 199 subtests, 1 optional skip, 0 failure/error/abort. 기존 데이터 복사본 foundation 검사 PASS. |
| 13 확장성 | **PARTIAL** | 신규 Native 실모델 발견→승인→실행→상관관계→제거 PASS, Provider 계약 PASS. Plugin/Skill 전체 수명주기는 이전 증거이며 이번에 독립 재실행하지 않음. |
| 14 lifecycle | **PARTIAL** | FPR-13 격리 설치/업데이트/복구 L6 PASS. 별도 클린 Windows Setup·첫 실행은 **BLOCKED**. |
| 15 P0/기반 P1 없음 | **FAIL** | 보안 P0 실측 0. 제품 GUI 도구 선택·grounding 반복 안정성 P1과 필수 L4/L5 공백이 남음. |

## 핵심 실행 증거

| 검증 | 결과 | 증거 |
| --- | --- | --- |
| 집중 계약 | 33 PASS, 17 subtests PASS + 18 self-check PASS | `.tmp/master08/contracts/contracts.log` |
| 전체 pytest | 1,299 PASS, 199 subtests PASS, 1 optional skip | `.tmp/master08/pytest/results.xml`, `pytest.log` |
| FPR-13 | 24 PASS, 1 product-home 분리 항목 UNVERIFIED; 분리 재실행 후 IDE PASS | `.tmp/master08/fpr13/results.json`, `product-home-fixed/results.json` |
| Native/MCP/mixed | 각 10/10 PASS | `.tmp/master08/native-10`, `mcp-10`, `mixed-10` |
| Gateway/MCP | 실제 모델 grounding, 승인, ownership, restart PASS | `.tmp/master08/gateway-mcp/gateway-result.json`, `gateway-restart/gateway-result.json` |
| MCP timeout | 4.841초, `execution_uncertain=false` | `.tmp/master08/mcp-timeout/mcp-timeout.json` |
| Memory GUI | 7/7 PASS, Wiki unchanged | `.tmp/master08/gui-memory/gui-chat.json` |
| Process GUI | 10/10 exit 0 | `.tmp/master08/process-10/` |
| 스트리밍 종료 | PASS | `.tmp/master08/gui-shutdown/gui-chat.json` |
| L7 Native | 실모델·승인·correlation·제거 PASS | `.tmp/master08/foundation-native/foundation-native.json` |
| 201p PDF | 87쪽 표식 정확 일치, 이웃 표식 없음 | `.tmp/master08/document/result.json` |

## 실패, 수정, 재시도

1. `gui-product-home` 최초 실행은 IDE 9단계를 실제 완료했지만 CP949 stdout이 U+FFFD를 인코딩하지 못해 exit 1이었다. 최초 로그는 `.tmp/master08/product-home/logs/ide_product_control.log`에 보존했다.
2. `iris/ui/_check_local_vibe_smoke.py`의 콘솔 JSON만 `ensure_ascii=True`로 바꿨다. UTF-8 증거 파일과 제품 동작은 유지했다. 동일 검사 재실행은 IDE 9/9와 정상 종료 PASS다.
3. 제품 GUI 도구 최초 실행은 Native 0/3, MCP PASS, mixed PASS, Shell은 실제 승인/실행 없이 표식만 답해 FAIL. `.tmp/master08/gui-tools/gui-chat.json`.
4. 재시도는 Native read·grounding은 성공했지만 search 생략, MCP PASS, mixed grounding FAIL, Shell 승인·실행·grounding PASS. `.tmp/master08/gui-tools-retry/gui-chat.json`.
5. 재시도는 최초 실패를 승격하지 않는다. 두 실행의 실패 양상이 달라 반복 안정성 결함으로 판정했다.

## Wave 2 의존성과 다음 수정 큐

1. **U07/U10 기반 차단:** 제품 GUI에서 선택된 eager tool과 실제 tool call을 상관 기록하고, 도구 실행이 필수인 요청에서 무도구 답변·가짜 stdout을 성공으로 착지시키지 않는 bounded recovery/실패 계약을 추가한다.
2. **U09 기반 공백:** Todo→실도구→host evidence, Clarify GUI 응답→resume, Delegate 권한/예산/취소를 실제 모델 제품 경로에서 반복 검증한다.
3. **U11 기반 공백:** 실제 OCR 한글/영문·혼합/손상/암호화/회전 및 Voice/TTS/vision 종료 시나리오를 L4/L5로 채운다.
4. 수정 후 제품 GUI Native/MCP/mixed/Shell과 전체 pytest/FPR-13을 최종 지문에서 다시 실행한다. 클린 Windows는 별도 환경에서 L6를 닫는다.

## 최종 판정

**WAVE 2 ENTRY: NO-GO.** 개발 중단이 아니라 위 기반 P1을 수정하고 해당 검사만 재실행하라는 판정이다.
