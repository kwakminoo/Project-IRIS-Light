# Prompt 시퀀스: Phase 5 in-process Prove → (조건부) Merge

기준: `docs/code-review/Iris-Agent-Phase5-in-process-검증계획.md`  
규칙: **채팅 하나 = Prove 하나.** 끝나면 결과만 보고하고 다음 Prove는 **새 채팅**에서.  
병합 전면 작업은 **Merge 채팅**에서만. Prove 중 `:8642` 제품 경로 삭제 금지.

장기: 초파리·git commit은 요청 있을 때만.

---

## 공통 (모든 채팅에 붙일 한 줄)

```text
@docs/code-review/Iris-Agent-Phase5-in-process-검증계획.md @docs/prompts/Iris-Agent-Phase5-prove-채팅시퀀스.md /poteto-mode
```

제약 공통:
- 한국어 요약. 커밋 금지(요청 전).
- qt-slot-abort / no-console-windows / thin launcher 유지.
- 클릭·사이드바 → 에이전트 턴 금지.
- 새 `hermes_*` 모듈 남발 금지. 가능하면 기존 worker·`agent_runtime` 확장.
- Prove FAIL이면 병합 착수하지 말고 고친 뒤 **같은 Prove를 새 채팅에서** 재실행.

---

## 채팅 A — Prove 0 (새 창에서 이것만)

```text
Feature: Phase5 Prove 0 only. Do NOT merge, do NOT remove :8642 product path.

Goal: Prove Iris Agent loop (or minimal stand-in that will become the in-process loop) can run on a worker thread without touching QWidget, using vendor pin / existing runtime home. Leave a small check module that fails if UI widgets are imported on the agent path.

Verify:
- .venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove0
- Existing phase1 / phase4b / phase2_5 still pass
- Report short: what was imported, whether HTTP :8642 was used (OK for Prove 0 to still use HTTP OR a stub — say which), bottlenecks seen

Out: docs/code-review/Iris-Agent-Phase5-prove0.md (structure + code review + borrow). Update prove checklist in the plan doc for Prove 0 only.
Stop. Do not start Prove 1.
```

---

## 채팅 B — Prove 1 (Prove 0 PASS 후 새 창)

```text
Feature: Phase5 Prove 1 only (Prove 0 already PASS).

Goal: Enforce thread boundary — agent worker must not block UI thread; exceptions in worker must not escape into MainWindow slots as uncaught. Add/extend check that documents the contract (signal-only to UI). Optional: intentional bad-path unit that would abort if called on UI — keep it out of live slots.

Verify:
- .venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove1
- .venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove0
- Note any freeze risk remaining

Out: docs/code-review/Iris-Agent-Phase5-prove1.md. Checklist Prove 1 only. Stop before Prove 2.
```

---

## 채팅 C — Prove 2 (Prove 1 PASS 후 새 창)

```text
Feature: Phase5 Prove 2 only.

Goal: (1) no visible console when agent path runs (reuse no-console contracts). (2) Agent-path exception is contained: worker emits failed / returns error dict; process must not require kill. Do not treat “crash kills all” as acceptable — fix containment.

Verify:
- .venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove2
- .venv\Scripts\python.exe -m unittest tests.test_no_console_window -v   (if applicable to touched path)
- Prior prove0+1 checks still pass

Out: docs/code-review/Iris-Agent-Phase5-prove2.md. Stop before Prove 3.
```

---

## 채팅 D — Prove 3 (Prove 2 PASS 후 새 창)

```text
Feature: Phase5 Prove 3 only.

Goal: Hot-restart substitute — reset/replace agent worker (or loop handle) while keeping a fake or real UI host object alive. Document which real “engine-only restart” cases are covered (gateway hang, config reload, soft-hang) and which still need full process restart (pin/code swap). Assert load_pinned_sha still matches vendor PIN.

Verify:
- .venv\Scripts\python.exe -m iris.system._check_iris_agent_phase5_prove3
- prove0–2 still pass

Out: docs/code-review/Iris-Agent-Phase5-prove3.md + flip plan doc “착수 조건” checkboxes that are now true. Explicit PASS/FAIL for “Merge allowed?”. Stop. Do NOT merge.
```

---

## 채팅 E — Merge (Prove 0–3 전부 PASS + 사용자 명시 후에만)

```text
Feature: Phase5 Merge — in-process default for speak path. Prove 0–3 all PASS (cite check names).

Goal: Product speak path uses in-process agent loop on worker thread; :8642 becomes fallback/dev only or removed from product default. Keep package split (ui vs agent). Keep reset API. No fruit-fly. Update §5 checklist in completed path doc or add Phase5-merge report.

Verify: all prove checks + phase1/2_5/3/4/4b + settings + hermes_required. Manual note if needed.

If any prove regresses: revert merge default, keep separate process.
```

---

## 사용 순서 (사람)

1. 새 채팅 → 공통 한 줄 + **채팅 A** 본문  
2. PASS면 새 채팅 → **채팅 B** …  
3. Prove 3까지 PASS + 계획서 착수 조건 충족 → 새 채팅 → **채팅 E**  
4. 중간에 FAIL → 같은 Prove 번호만 새 채팅에서 재시도
