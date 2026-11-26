# PHASE 17 Gate B Negative Contracts

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE17-GATE-B-NEG-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | R-GATE-B · R-NAT-FIG09 · residual tracker · FPR registry 차단 |
| 대상 | 제품 sidecar Hermes registry 래퍼 · Speak/agent invoke · confirm_required 승인 |
| 목적 | Gate B 네거티브 계약(미등록·Hermes 원본·승인 우회)을 `_check_*`로 잠그고 실측 |

## 1. 결론

R-GATE-B / R-NAT-FIG09 네거티브 묶음은 **녹색**이다. Hermes 원본 이름(`apply_patch`, `clarify`, `patch`)은 제품 설치 후 registry dispatch가 `TOOL_NOT_AVAILABLE`을 내고 Hermes 본체를 치지 않는다. 미등록 Speak/agent invoke는 `not_allowed` / `unknown tool`로 거절된다. strip-only(`clarify`)는 Control action·엔진 스키마에 없다. `confirm_required` 액션은 모델 `confirm:true`만으로 승인되지 않는다.

live 엔진·`legacy_migration_approved`는 건드리지 않았다. 커밋/푸시 없음.

## 2. 실측 (GateBReport)

| id | surface | invoke | expect | measured | check | exit |
|---|---|---|---|---|---|---|
| GB-HERMES-01 | sidecar registry wrap | `apply_patch` | blocked `TOOL_NOT_AVAILABLE` | ok, hermes_hits=[] | `_check_native_tool_hermes_disabled` | 0 |
| GB-HERMES-02 | sidecar registry wrap | `clarify` | blocked `TOOL_NOT_AVAILABLE` | ok | 同上 | 0 |
| GB-HERMES-03 | sidecar registry wrap | `patch` | blocked `TOOL_NOT_AVAILABLE` | ok | 同上 | 0 |
| GB-UNREG-01 | SpeakTools | `unregistered_gate_b_tool` | denied `not_allowed` | ok | 同上 | 0 |
| GB-UNREG-02 | agent_tool_registry | `unregistered_gate_b_tool` | denied `unknown tool` | ok | 同上 | 0 |
| GB-INACT-01 | absorbed aliases | `clarify` resolve / schemas | inactive (None / absent) | ok | 同上 | 0 |
| GB-APPR-01 | execution_policy | `email.send` + `confirm:true`, human=None | denied `human confirm required` | ok | hermes_disabled + `_check_execution_policy` | 0 |
| GB-APPR-02 | request_approval ledger | consume without grant / fp mismatch | denied | ok | `_check_request_approval` | 0 |
| GB-SCHEMA | tool contract | engine schemas SSOT | still green | ok | `_check_tool_contract` | 0 |

체크 출력 (measured):

```
native_tool_hermes_disabled ok blocked=apply_patch,clarify,patch gate_b=unregistered,inactive,approval_refuse
execution_policy ok
request_approval ok
tool_contract ok
```

## 3. 구조

요청(위험 도구 / 미등록 이름 / 승인 우회) 경로:

```
model / sidecar tool call
  ├─ product install wrap (tools.registry.dispatch)
  │     → TOOL_NOT_AVAILABLE   ✂ Hermes 원본·미등록 이름
  │     ✂ hermes_hits must stay []
  ├─ SpeakTools.invoke(allowlist)
  │     → not_allowed          ✂ 미등록 / 비허용
  ├─ IrisAgentToolRegistry.invoke
  │     → unknown tool         ✂ 미등록
  ├─ resolve_action / engine_tool_schemas
  │     → None / 미포함        ✂ strip-only inactive
  └─ ActionRegistry + check_action_approval
        → human confirm required ✂ confirm:true 단독 우회
```

이번 Gate B가 잠그는 갈라짐: **원본 Hermes dispatch 성공 경로**와 **모델 confirm만으로 high-risk 통과**.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한/막은 이유 |
|---|---|---|
| `_install_iris_engine_tools` registry wrap | 원본 이름을 `TOOL_NOT_AVAILABLE` JSON으로 반환 | Hermes `HERMES_RAN` 경로를 교체해 차단 (막음) |
| `_check_native_tool_hermes_disabled` | MUST_BLOCK 3이름 + unreg/inactive/approval assert 추가 | 예전엔 집합 “첫 원소”만 찍어 계약이 느슨했음 → 핀 고정 |
| `SpeakTools.invoke` | allowlist miss → `not_allowed` | 미등록이 Control surface에 닿기 전 거절 |
| `invoke_agent_tool` | unknown → `ok:false` | 네이티브 핸들러 없는 이름 거절 |
| `check_action_approval` | human=None이면 deny | 모델 `confirm` 키는 pop 후 권한 아님 |
| `_check_execution_policy` / `_check_request_approval` | 기존 승인·ledger 거절 유지 | Gate B 승인 축 재실행만 (신규 프레임워크 없음) |

하지 않은 일: live engine 변경, Hermes 원본 파일 삭제, `legacy_migration_approved` 승격, 새 테스트 프레임워크, Control HTTP E2E.

## 5. 개선안

| 빈 자리 | 내용 |
|---|---|
| 라이브 턴 증거 | 계약은 green. 실제 모델이 strip/미등록 이름을 호출했을 때 agent.log `TOOL_RESULT` 한 줄은 UNVERIFIED |
| residual tracker 상태 | R-GATE-B / R-NAT-FIG09를 이 문서 기준으로 COMPLETE(계약)로 갱신하는 절차는 별도 |
| 전수 strip-only | 지금은 `clarify`·스키마 부재만 잠금. 15개 STRIP_ONLY 전수 invoke는 비용 대비 후순위 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| 기존 `_check_native_tool_hermes_disabled` | registry wrap 시뮬 + TOOL_NOT_AVAILABLE | 이미 SSOT. 확장만 |
| `_check_execution_policy` | confirm self-approve 거절 | 중복 러너 불필요. 번들에 포함 |
| pytest/hypothesis property 스위트 | 임의 도구 이름 fuzz | 계약 핀 3+미등록이면 Gate B 닫힘. fuzz는 과함 |
| 찾지 못함 | Gate B 전용 외부 오픈소스 하네스 | 제품 `_check_*`로 충분 |

## 7. 조치

1. `_check_native_tool_hermes_disabled`에 Gate B 핀·미등록·inactive·approval assert 반영 (완료).
2. 포커스 묶음 재실행 exit 0 기록 (완료).
3. residual tracker의 R-GATE-B / R-NAT-FIG09를 계약 COMPLETE로 옮기는 갱신은 메인 조율 시.
4. 라이브 모델 턴 negative는 R-OBS-FIG04 / 13FPR과 묶을 것. 이번 범위 밖.
5. commit/push · live engine · migration 승격 — 금지 유지.
