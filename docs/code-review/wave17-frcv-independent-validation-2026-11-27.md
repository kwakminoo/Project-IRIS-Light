# FRC Final Independent Validation (진행 중)

| 항목 | 내용 |
|---|---|
| 문서 번호 | FRCV-WAVE17-2026-11-27 |
| 작성일 | 2026-11-27 |
| 관련 | FRC-09 Independent Validation · Wave 2 Entry Gate |
| 대상 | HEAD `619f876` + dirty fingerprint `0716ad62…` |
| 목적 | 구현 COMPLETE를 불신하고 실증거로 Wave 2 Entry 판정 |

## 1. 결론

**최종 판정: NO-GO** — [FRCV-13 Verdict](wave17-frcv13-wave2-entry-verdict-2026-11-27.md) · [증거 색인](wave17-frcv12-evidence-index-2026-11-27.md).

근거 (실측):

1. Git HEAD가 직전 기준선 `619f876`와 **동일**. FRC 구현은 **커밋되지 않은 dirty tree**(26파일, fingerprint `0716ad62ec3627a46ee818b4800dc22d6555ca60ee5485c69848c6619cd35c8a`)에만 존재한다.
2. 구현 트래커의 FRC-01A/B COMPLETE는 **L2 unittest + 격리 L4 post-cutoff MCP/Native 2/2**까지는 재확인됐다. 그러나 **Mixed 1/1 FAIL**이 남아 있고, 제품 기본 모델 환경과 격리 실험 환경이 다르다.
3. 제품 `agent/config.yaml` 기본 모델은 `gemma4:e2b`인데, 로컬 Ollama 목록에 **해당 태그가 없다** (`gpt-oss:20b`, `gemma4:12b` 등은 있음). 제품 기본 환경 L4를 아직 PASS로 칠 수 없다.
4. 제품 기본 `disabled_toolsets`에 `terminal`/`browser`/`file`/`memory`/`delegation`/`clarify`/`vision` 등이 포함되어 있다. 핵심 Native·Agent Intelligence를 제품 기본으로 PASS 선언하면 안 된다.
5. Webhook/Connector 코드 검색(`iris/` webhook|connector) **무일치** → FRC-04A **OPEN** 유지.
6. `legacy_migration_approved=false`. live `iris-agent` 디렉터리 python **없음**, legacy `hermes-agent` python **존재**.
7. L2 계약 자검 오늘 재실행: adaptive_context / turn_todo / schema_refuse / pdf_page_range / frc06_panel_land / gateway_legacy / absorbed aliases+wire → **전부 PASS**. 이는 L5/L4 제품 PASS가 아니다.

## 2. FRCV-00 Baseline (고정)

| 항목 | 값 |
|---|---|
| Actual Git HEAD | `619f876d06fcf51ea0ea03e8148d30feb1c0e3a1` |
| Working Tree | dirty (26 paths) |
| Source Fingerprint | `0716ad62ec3627a46ee818b4800dc22d6555ca60ee5485c69848c6619cd35c8a` |
| Vendor Core | `0.1.2+iris.a382af23` / upstream `a382af23…` |
| Active Slot | `iris-agent.slot-272facc0f5fd4b6f` |
| Previous Slot | `iris-agent.slot-e38f3ea761714c36` |
| Agent Python | 3.14.7 (slot venv) |
| AIAgent Import | `run_agent.py` |
| MCP SDK | 2.3.0 |
| SOURCE_MANIFEST | slot ≡ vendor, `legacy_migration_approved: false` |
| Product Provider | custom → `http://127.0.0.1:11434/v1` |
| Product Model | `gemma4:e2b` (설치 여부: **미확인/목록 없음**) |
| Prior ACF Model | `gpt-oss:20b` (설치됨) |
| Effective Context (config) | `ollama_num_ctx: 64000` (실효 토큰 분해는 FRCV-01 추가 측정) |

증거: `.tmp/frcv/frcv00-baseline.json`

## 3. FRCV-01 초기 증거

### 3-1. 직전/기존 L4 인덱스 (재집계, 새 실행 아님)

| Suite | Result |
|---|---|
| post-cutoff-mcp | 2/2 PASS |
| post-cutoff-native | 2/2 PASS |
| post-cutoff-mixed | 1/1 FAIL (local.search_files scope 밖 → MCP만) |
| compact-mcp / compact-native | 3/3 PASS each |
| adaptive-* (조기) | FAIL |

지수: `.tmp/frcv/frc-prior-results-index.json`

### 3-2. L2 재실행 (오늘)

`tests.test_wave17_adaptive_context` → 2 OK.

### 3-3. 제품 기본 환경 게이트

| 검사 | 상태 |
|---|---|
| Ollama에 `gemma4:e2b` | **목록 없음** → 제품 기본 L4 **BLOCKED/FAIL 후보** |
| Ollama에 `gpt-oss:20b` | 있음 (이전 ACF/FRC 격리에 사용) |
| disabled_toolsets | file/terminal/memory/delegation/clarify 등 비활성 → 제품 기본 핵심 작업 **제한** |

## 4. 금지 규칙 준수 메모

- Mock을 L4 PASS로 쓰지 않음.
- L2 PASS를 GUI/제품 PASS로 승격하지 않음.
- post-cutoff 격리 성공을 제품 기본(`gemma4:e2b`) PASS로 쓰지 않음.
- Mixed FAIL을 숨기지 않음.
- Webhook 미구현을 Discovery PASS로 위장하지 않음.

## 5. FRCV-05 / FRCV-08 (독립 재검)

증거: `.tmp/frcv/frcv05-08-evidence.json`

| 영역 | 상태 | 요지 |
|---|---|---|
| Schema refuse after approval | PASS | L2 |
| Gateway legacy isolated / no spawn / retired surface | PASS | L2 |
| Approval replay / fingerprint mutation | PASS | L2 |
| Webhook + Connector | OPEN | `iris/` 구현 0 |
| `_check_product_no_iris_control_mcp` | FAIL | memory nudge가 tool_search 문구로 바뀌어 SpeakTools assert 실패 |
| `_check_speak_tools_no_mcp_seed_path` | FAIL | `wiki.list_notes`에 `limit` 거부 |
| Canonical `iris-agent` live dir | MISSING | 슬롯 선택은 동작; hermes-agent python은 디스크에 잔존 |
| FRCV-05 / FRCV-08 종합 | PARTIAL | |

## 6. 결함 분류 (초기 보존)

### P0

없음 (현재까지).

### P1

| ID | 내용 |
|---|---|
| PRODUCT-MODEL-MISSING | 제품 기본 `gemma4:e2b` Ollama 404 |
| PRODUCT-TOOLSETS-DISABLED | 제품 config가 file/terminal/memory/delegation/clarify 등 비활성 |
| FRC-04A | 서명 Webhook·Connector 미구현 |
| MCP-CONTRACT-2 | 위 두 계약 검사 FAIL (수정 루프 진행 중) |
| FRC-01-MIXED | Native+MCP mixed FAIL |
| ABSORB-12/15 | 15개 중 3 BOUND, 나머지 MISSING/ALIAS/BLOCKED |
| FRC-08W | 클린 Windows BLOCKED |

### P2

- 문서/트래커 COMPLETE 과대 표기
- Canonical iris-agent 디렉터리 부재(슬롯으로 완화)

## 7. 남은 작업

- FRCV-02/03/06/07/10 서브에이전트 산출 흡수
- dirty tree에서 gpt-oss native/mcp 재실측
- FRCV-11 가역 P1 수정 후 재검증
- FRCV-12 증거 패키지 · FRCV-13 Wave 2 Gate

## 8. 조치 (현재)

1. Wave 2 Entry **GO 선언 금지**.
2. 제품 기본 모델 태그 불일치(`gemma4:e2b` 미설치)를 P1으로 추적. 사용자 Ollama 설정을 무단 변경하지 않음.
3. 검증 대상 SHA/Fingerprint를 dirty tree로 고정하고, 수정 발생 시 해당 범위만 재검증.
4. 계약 검사 2건 FAIL은 초기 결과를 보존한 채 수정 후 재검.
