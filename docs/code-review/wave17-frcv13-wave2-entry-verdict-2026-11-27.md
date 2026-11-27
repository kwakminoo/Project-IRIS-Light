# Wave 2 Entry Verdict — Independent Validation

| 항목 | 내용 |
|---|---|
| 문서 번호 | FRCV-13-WAVE2-2026-11-27 |
| 작성일 | 2026-11-27 |
| 관련 | FRCV-00~12 · FRC-09 Independent Audit |
| 대상 | HEAD `619f876` + dirty fingerprint `5d0e441f…` (최종 재검증 시점) |
| 목적 | Wave 2 Entry Gate 객관 판정 |

## 1. 결론

**WAVE 2 VERDICT: NO-GO**

Owned Core 런타임·격리 gpt-oss Native/MCP·다수 L2 계약은 살아 있다. 그러나 Wave 2 Entry에 필요한 기반 게이트가 여러 개 미달이다. 구현 트래커의 COMPLETE를 독립 재검으로 승격하지 않는다.

초기 검증 지문 `0716ad62…`(26파일)을 보존했다. FRCV-11에서 계약 검사 2건을 고친 뒤 최종 판정 지문은 `5d0e441f40b481f2f87679151812f3bc93d7c558e88644b3ecf1cf9278f2d5f7`(29파일)이다. Git HEAD는 계속 `619f876`이며 FRC 코드는 미커밋이다.

## 2. 판정에 쓴 원칙

| 원칙 | 선택 |
|---|---|
| Prove It Works | 트래커 COMPLETE 대신 재실행·디스크 증거만 인정 |
| Attack the Premise | “FRC-01 COMPLETE = 제품 기본 환경도 OK” 전제를 깨고 제품 모델/툴셋 실측 |
| Guard the Context Window | 영역별 서브에이전트 + `.tmp/frcv/` 증거 |
| Laziness Protocol | P1 계약 FAIL은 검사/스키마 정합만 수정 (기능 신설 없음) |

## 3. 기준선 (FRCV-00)

| 항목 | 값 |
|---|---|
| HEAD | `619f876d06fcf51ea0ea03e8148d30feb1c0e3a1` (= 직전 baseline) |
| 최종 fingerprint | `5d0e441f…` |
| Active slot | `iris-agent.slot-272facc0f5fd4b6f` |
| Core | `0.1.2+iris.a382af23` · MCP 2.3.0 · Python 3.14.7 |
| `legacy_migration_approved` | false |
| 제품 모델 | `gemma4:e2b` (**Ollama 404**) |
| 검증 모델 (격리) | `gpt-oss:20b` (설치됨, advertised ctx 131072) |

## 4. GATE 01–15

| Gate | 판정 | 근거 (측정) |
|---|---|---|
| 01 Runtime Independence | **PASS*** | 선택 엔진=owned slot. sidecar-only·gateway spawn 금지 계약 PASS. hermes-agent 디스크 잔존은 정상 경로 비의존으로 기록 |
| 02 Functional Absorption | **FAIL** | 15개 중 L3 PASS 3 · FAIL 5 · PARTIAL 7 · L4 0 |
| 03 Model Context | **FAIL** | 제품 기본 `gemma4:e2b` 미설치. disabled_toolsets에 file/terminal/memory/delegation/clarify. 격리 gpt-oss만 PASS |
| 04 Agent Intelligence | **FAIL** | Todo 도메인 L2만. Memory/Clarify/Delegation 제품 미완. `Engine.fork`≠Delegation |
| 05 Multi-step Quality | **PARTIAL / UNVERIFIED** | dirty tree 재실측 Native 2/2 PASS, MCP 2/2 PASS. Mixed 하네스 FAIL(액션 순서)이나 응답에 Native+MCP 마커 동시 존재. 10회 반복 미달 → 반복 안정성 UNVERIFIED |
| 06 Native Gateway | **PARTIAL** | 토큰/승인/재시작 계열 계약 다수 PASS. 서명 Webhook·Connector **OPEN** |
| 07 MCP Ecosystem | **PARTIAL** | 격리 MCP 2/2 PASS · schema refuse PASS. GUI 전과정 L5·dual-server·재연결 잔여 |
| 08 Document Intelligence | **FAIL** | page-range L2 PASS. 201p 추가분석 L4 증거 없음. 추출 캐시 없음 |
| 09 Product Stability | **FAIL** | panel_land L2 PASS. 기존 36 pytest FAIL 미해소 증명 없음. `_log` 21건 skip≠해결. GUI 전수 L5 미완 |
| 10 Legacy Retirement | **PARTIAL** | 핫패스 Hermes 비의존 계약 PASS. hermes-agent·진단 EXE 경로 잔존. migration false |
| 11 Product Regression | **FAIL** | 핵심 계약 다수 PASS(수정 후 포함). 전체 pytest/FPR13 live·GUI 미충족 |
| 12 Lifecycle | **PARTIAL** | 격리 L6 이전 증거 PASS · Setup 0.1.18 해시 일치. 클린 OS FRC-08W **BLOCKED** |
| 13 Extensibility | **UNVERIFIED** | Wave 2 U07–U11 의존은 문서상 존재. Native/Provider/Plugin 확장 fixture 실측 미완 |
| 14 Security | **PARTIAL** | approval replay·schema drift refuse PASS. 전체 진입점 음성 매트릭스·GUI MCP 승인 E2E 미완. P0 보안 위반 실측 0 |
| 15 Final Defect Gate | **FAIL** | 미해결 P1 다수 (아래). P0 보안 우회는 현재 없음 |

\*01은 “외부 Hermes 필수 의존 제거” 관점 PASS. 레거시 파일 잔존은 Gate 10 PARTIAL로 분리.

## 5. FRCV 영역 요약

| ID | Status | 핵심 증거 |
|---|---|---|
| FRCV-00 | PASS (baseline fixed) | `.tmp/frcv/frcv00-baseline.json`, `frcv00-01-evidence.json` |
| FRCV-01 | PARTIAL | L2 adaptive OK · gpt-oss post-cutoff/revalidate Native+MCP PASS · Mixed/제품기본 FAIL |
| FRCV-02 | FAIL/PARTIAL | `.tmp/frcv/frcv02-03-matrix.json` — 3/15 |
| FRCV-03 | FAIL/PARTIAL | Todo L2 only |
| FRCV-04 | UNVERIFIED (reps) / PARTIAL | revalidate native/mcp 2/2; mixed harness FAIL; n≪10 |
| FRCV-05 | PARTIAL | webhook OPEN; contracts mostly PASS after FRCV-11 |
| FRCV-06 | PARTIAL/FAIL | no 201p L4 |
| FRCV-07 | PARTIAL/FAIL | skip≠PASS; 36 failures unresolved |
| FRCV-08 | PARTIAL | legacy isolated PASS; hermes residual |
| FRCV-09 | UNVERIFIED | extension fixtures not executed |
| FRCV-10 | PARTIAL | L6 prior + contracts; clean OS BLOCKED |
| FRCV-11 | DONE (limited) | 계약 2건 수정·재검 PASS — `.tmp/frcv/frcv11-p1-contract-fix.json` |
| FRCV-12 | THIS PACKAGE | docs + `.tmp/frcv/` |

## 6. 오늘 재실측 (gpt-oss:20b, dirty tree)

| Suite | Attempts | Harness | Notes |
|---|---:|---|---|
| native | 2 | PASS | `.tmp/frcv/revalidate-native` |
| mcp | 2 | PASS | `.tmp/frcv/revalidate-mcp` |
| mixed | 1 | FAIL | 응답에 Native+MCP 마커 모두 존재. 성공 액션 시퀀스 조건 불일치 |

## 7. FRCV-11 수정 (초기 FAIL 보존 후)

| Before | After |
|---|---|
| `_check_product_no_iris_control_mcp` FAIL | PASS — tool_search/tool_describe 경로 인정, iris-control 금지는 유지 |
| `_check_speak_tools_no_mcp_seed_path` FAIL | PASS — `wiki.list_notes`를 `{}`로 스키마 정합 |

코드 변경은 검사 정합만. iris-control MCP 복구 없음.

## 8. 미해결 P1 (Wave 2 기반을 막는 항목)

1. 제품 기본 모델 `gemma4:e2b` 미설치 + 핵심 toolset 비활성
2. Functional absorption 12/15 미완 (특히 clarify/delegate/memory/todo Speak)
3. FRC-04A Webhook/Connector 미구현
4. Mixed Native+MCP 안정 완료 기준 미달 (하네스·반복)
5. 201페이지 PDF 추가 분석 L4 부재
6. 기존 36 pytest / `_log` skip 잔여 → 제품 안정 PASS 불가
7. FRC-08W 클린 Windows BLOCKED
8. Wave 2 확장 fixture 실측 부재

## 9. CONDITIONAL GO가 아닌 이유

핵심 Agent 실행 기반(제품 기본 모델·흡수·오케스트레이션·문서 L4·회귀)이 열려 있다. 선택형 외부 Provider/서명만 남은 상태가 아니다. 따라서 CONDITIONAL GO로 숨기지 않는다.

## 10. Production Gate 분리

공개 배포·코드 서명·전체 사용자 마이그레이션은 Wave 2 Entry와 분리한다. 이번 NO-GO는 공개 배포 거부가 아니라 **Wave 2 제품 착수 거부**다.

## 11. 조치

1. Wave 2 기능 구현·`legacy_migration_approved` 승격·커밋/push는 하지 않는다 (요청 전).
2. 다음 구현 큐(우선): 제품 기본 모델/툴셋 정합 → absorption/agent intelligence → mixed 안정 → 201p PDF → 회귀 36 → webhook/connector → 확장 fixture.
3. 증거 루트: `docs/code-review/wave17-frcv-independent-validation-2026-11-27.md`, `.tmp/frcv/`.
