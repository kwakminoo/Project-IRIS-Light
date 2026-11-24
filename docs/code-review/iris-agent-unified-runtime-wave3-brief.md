# IRIS Unified Agent Runtime — Wave 3 상세 브리프 (U12–U16)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-24-AGENT-RUNTIME-W3 |
| 작성일 | 2026-11-24 |
| 관련 | [wave2 brief](iris-agent-unified-runtime-wave2-brief.md), Wave 1 U00–U06 |
| 대상 | U12 Headless/Sandbox · U13 Trajectory · U14 Batch/Eval · U15 Dataset Export · U16 Final Validation |
| 목적 | 학습·헤드리스 인프라 구현 계약을 고정한다. **코드 착수는 Wave 2 (U07–U11) green 이후.** |

## 1. 결론

Wave 3는 제품 GUI와 분리된 **연구/헤드리스 경로**다. 제품 대화 자동 학습 편입 금지, 실제 격리 없는 환경을 sandbox라고 부르지 않기, 문장만으로 성공 판정 금지가 게이트다. 이 문서는 Wave 1 완료·Wave 2 브리프 확정 시점에 작성했으며, Wave 2 구현 green 전에는 U12+ 코드를 시작하지 않는다.

## 2. 확인한 사실

| 항목 | 상태 |
|---|---|
| InternalSidecar / SpeakTools | Wave 1 유지 |
| ExecutionRuntime | U05 Local Subprocess + process_manage |
| FilePatch | U06 apply_patch |
| `scripts/iris_hermes_bench` | 존재; live 메트릭 U00 공란 |
| vendor trajectory / batch_runner | **없음** (PIN overlays only) |
| Aloha TrajectoryManager | GUI 학습용, Hermes bench 아님 |
| Wave 2 코드 | **미착수** (브리프만) |

## 3. 구조

```
IRIS Desktop / IDE / CLI
        │
 Iris Agent Core (제품과 동일 루프)
        │
 Policy + Tool Registry + Execution Runtime
        │
   ┌────┴────┐
   │         │
 Desktop   Headless CLI / Sandbox Backend   ← U12
   │         │
   │    Trajectory Recorder                 ← U13
   │         │
   │    Batch Runner + Evaluator            ← U14
   │         │
   │    Dataset Export (SFT/DPO/RL meta)    ← U15
   │         │
   └──── Final Validation                   ← U16
```

제품 대화 DB와 연구 Trajectory 저장소를 **분리**한다.

## 4. 코드 리뷰 (착지 예정 지점)

| 지점 | 현재 | Wave 3 |
|---|---|---|
| Sidecar / Fake Agent 테스트 | 제품 턴 | Headless가 같은 루프 재사용 |
| Control GUI actions | SURFACE 다수 | 서비스 계층 분리; GUI-only는 구조화 오류 |
| `execution_runtime` | Local Subprocess | Temporary workspace + (실제 지원 시) Docker |
| Bench scripts | iris_hermes_bench | IRIS Tool Registry 사용하도록 통합 |
| Persistence | 제품 채팅 | 연구 모드 Recorder만 |

하지 않은 일: CLI 패키지, Trajectory 스키마, 대량 API 교사 호출.

## 5. 단위 브리프

### U12 — Headless Runtime & Sandbox

**Gate:** Wave 2 green  
**Change:** `python -m iris.cli` (run/exec/tools/doctor) — 최종 서브커맨드는 기존 구조 분석 후 확정. Sandbox Backend: Temporary Workspace(비보안 표기), Limited Local, Docker(지원 시만). Mock email/calendar/wiki/fixture web. 시나리오 후 리셋.

**Verify:** GUI 없이 명령 실행; GUI-only 도구 구조화 오류; 격리 주장 테스트는 실제 메커니즘만.

### U13 — Trajectory Recorder

**Gate:** U12  
**Change:** 연구 모드 전용. 모델 요청 전후·tool_call·native bridge·결과·승인·압축·턴 종료 훅. ID 연결: trajectory/run/session/turn/step/model_call/tool_call/process. PII·시크릿 기록 단계 제거. Recorder 실패가 제품 턴을 죽이지 않음; 연구 모드에서는 불완전 궤적 성공 채택 금지.

**Verify:** 한 작업 이벤트 재구성; tool_call_id 연결; PII 스캔.

### U14 — Batch Runner & Evaluation

**Gate:** U13  
**Change:** Scenario / Environment / User Simulator / Teacher / Scheduler / Collector / Evaluator / Resume. 성공은 파일·테스트·patch·프로세스·권한으로 판정. 공개 벤치(BFCL, SWE-bench 등)는 라이선스 확인 후. Eval/Train 분리.

**Verify:** 소규모 시나리오 10건; 문장-only 성공 판정 실패 assert.

### U15 — Dataset Export

**Gate:** U14  
**Change:** Canonical JSONL, OpenAI messages, ShareGPT, preference pair, RL meta. SFT는 검증된 성공 중심. DPO는 동일 초기조건 성공/실패. Assistant-only loss masking 가능 형태. 품질 게이트: schema·도구명·순서·PII·중복·split·라이선스.

**Verify:** 100건 품질 통과 후 1000 pilot 확대 가능 여부만 보고; 무단 대량 유료 API 금지.

### U16 — Final Validation

**Gate:** U11 + U15  
**Change:** 제품·런타임·랩 체크리스트 실행. Skip은 성공 집계 금지. U00와 동일 모델로 전후 비교(메트릭 있을 때).

**Verify:** 회귀 스위트 + 라이브 샘플; 저하 작업 원인 기록.

## 6. 개선안 (빈 자리)

1. Headless CLI 엔트리 없음.
2. Trajectory/Batch 코드 없음 (vendor에도 없음).
3. 제품/연구 데이터 분리 정책 코드화 전.
4. Live baseline 메트릭 공란.

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Hermes agent/trajectory.py | 이벤트 스키마 | PIN에 없으면 IRIS 스키마 신설 |
| Hermes batch_runner | 스케줄/resume | 도구는 IRIS Registry로 교체 |
| iris_hermes_bench | 시나리오·aggregate | 제품 효과 판정 유지 |
| BFCL / SWE-bench / AgentDojo | 평가 설계 참고 | 라이선스·데이터 혼입 금지 |
| Docker SDK | 실제 격리 | 미설치 환경에서 지원 표기 금지 |

## 8. 조치

1. **Wave 2 U07–U11 green 전까지 이 문서의 구현 착수 금지.**
2. Wave 2 완료 후 U12 실패 체크부터 TDD.
3. 연구 모드 동의·PII 게이트를 U13 이전에 문서화·코드화.
4. 최종 시 README·아키텍처 문서를 구현에 맞게 갱신 (문서만으로 완료 주장 금지).
