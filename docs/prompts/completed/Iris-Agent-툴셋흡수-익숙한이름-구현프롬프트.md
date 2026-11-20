# Prompt: Iris Agent 툴셋 흡수 — 익숙한 이름 + Iris 구현 (A)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-19 |
| 관련 | 채팅 일체화 후 모델이 Hermes 네이티브 툴을 선호하는 문제, `:8642` 잔재, Speak/PHASE4 |
| 대상 | sidecar 툴 카탈로그 · file/terminal 표면 분기 · web 유지 · `:8642` 문자열 청소 |
| 목적 | 모델엔 익숙한 toolset/함수 이름만 보이게 하고, file/terminal 실행은 100% Iris Control |

관련 정본: `docs/code-review/Iris-Agent-tool-window-unify-2026-11-18.md`, Phase1 NO-GO, Phase5 Merge NO.  
선행: NVIDIA `options` 가드 PR(#44) — 제품 `ensure_ready` soft-patch. 이 프롬프트와 충돌 시 가드 유지.

```text
/poteto-mode

## Goal
Product chat AIAgent shows a familiar Hermes-shaped catalog (toolset file/terminal/web/…)
but file+terminal handlers are Iris-only (Control). No upstream Hermes file/terminal
handlers on the product path. Keep Hermes web_search/web_extract. Leave other
non-overlapping upstream toolsets as-is. Strip :8642 / gateway residue strings so no
product surface implies that HTTP gateway. Shrink MEMORY nudge FS/shell "use SpeakTools"
sermons once familiar names are Iris-backed.

## Domain shape (fixed — do not reinvent)

Model-visible:
  toolset file      → write_file, read_file, search_files  (+ patch only if Iris-backed or drop)
  toolset terminal  → terminal  (not process_manage unless Iris-backed)
  toolset web       → web_search, web_extract   # KEEP upstream Hermes implementation
  other toolsets    → leave registered as today if they do not overlap Speak FS/shell
  Iris-only         → wiki/ide/diagram/app/… under a non-colliding toolset (e.g. iris)
                      OR keep current Speak names only for non-overlapping actions

Implementation:
  file/* and terminal → Control invoke by speak_surface
    home:  FS under home/allowed roots; terminal → shell.run (Iris Shell card, CREATE_NO_WINDOW)
    ide:   project.write_file / read_file / list_files; terminal → project.run
  web/* → upstream Hermes handlers OK (user decision: no Speak search stack)
  agent.tools on product sidecar = REPLACE catalog for file+terminal slots with Iris
    adapters; do NOT union Hermes file/terminal + Speak project_*/shell_run
  control.invoke: may leave as internal bus; remove or keep as model-visible only if needed
    for escape hatch — default prefer NOT exposing it once file/terminal are familiar names
  Speak PHASE4 grants remain the capability registry internally; model menu uses familiar names

Runtime shell (unchanged):
  InternalSidecar + AIAgent from pin. No Qt same-process merge. No :8642 product start.

## Why (evidence)
- Sidecar disables file/terminal then ADDS SpeakTools → union; local models prefer
  write_file/terminal over project_write_file/shell_run
- Live config had tool_choice=required amplifying familiar picks
- Hermes file/terminal are NOT product-superior (wrong root, console, no Companion)
- Hermes web IS the real search stack; Speak has no equal — keep it

## Constraints
- Do NOT re-enable Hermes file/terminal handlers
- Do NOT put both write_file and project_write_file on the model schema
- no-console-windows, qt-slot-abort, hermes-chat-landing, thin IRIS.exe launcher
- Phase1 process NO-GO / Phase5 Merge NO
- Commit only if user asks
- Fresh poteto-agent per TDD unit; main verifies checks
- Korean summaries
- **Gate:** never start Unit N+1 until Unit N passes both automated checks AND live Iris smoke (below)

## Per-unit gate (mandatory — after each Unit 0…6)

Sequence for every unit (do not skip; matches project TDD-repro-fix + verify-iris):

```
Unit N implement (fresh poteto-agent, fail→pass checks)
  → Main re-runs that unit's checks
  → Restart Iris (thin launcher / pythonw -m iris) so sidecar loads new code
  → Live smoke (verify-iris / control HTTP / one chat turn as unit needs)
  → Broken? STOP the absorption ladder
       → Bug-fix playbook: reproduce → root cause → fix → PR
       → Re-run unit checks + same live smoke until green
       → Only then Unit N+1
  → Green? Record evidence path, then Unit N+1
```

Live smoke minimum (adjust per unit; always after restart):

| After unit | Must still work |
|---|---|
| 0–1 | Iris boots; doctor/control live; one short chat turn lands (assistant row) |
| 2 | Home: familiar write/terminal → Iris path (Shell card / home FS). IDE: write/terminal → project.* / project.run |
| 3 | Model catalog has no overlapping Speak names; chat still tools OK |
| 4 | web_search still callable; non-overlap toolsets not wiped |
| 5 | Nudge sync OK; no regression on wiki/ide teaching path |
| 6 | No user-facing :8642; chat still sidecar (not gateway start) |

Proof path: prefer `.cursor/skills/verify-iris` (`doctor.py`, `prove_feature.py`, `invoke.py`) and landing contracts
(`_check_chat_landing_contract`, `_check_sidecar_done_landing`) over ad-hoc clicks.
If live surface cannot be driven, say why after exhausting control skill — then instrument.

Bug-fix when smoke fails:

- New worktree off trunk (or stack on current absorption branch if user says so)
- Bug-fix playbook + Opening a PR
- Do not "paper over" with extra disable lists; fix root cause
- Absorption Unit N+1 stays blocked until that PR is verified green on the same smoke

## Implementation units (TDD, order fixed)

### Unit 0 — Contract table + failing checks
- Encode mapping table in one module (e.g. iris/engine/familiar_tools.py or similar):
  familiar name → (toolset, surface → Control action or Hermes-keep flag)
- Self-check: home/ide mappings for write_file/read_file/search_files/terminal
- Self-check: web_search/web_extract marked keep-upstream
- Fail until catalog builder uses this table

### Unit 1 — Sidecar catalog replace (file + terminal)
- After AIAgent construct: product path replaces file+terminal entries with Iris adapters
  (or builds tools list so Hermes file/terminal never appear)
- valid_tool_names matches
- Check: scrape/mock ensure no upstream file/terminal handler registration on product tools list
- Check: write_file/terminal present with Iris adapter marker/toolset ownership iris-or-familiar-owned

### Unit 2 — Surface dispatch
- home write_file/read_file/search_files → home-scoped Iris actions (local.* / agreed home FS)
- ide → project.write_file / project.read_file / project.list_files
- home terminal → shell.run (Shell card, no console)
- ide terminal → project.run
- Unit tests with speak_surface home vs companion; no live NVIDIA required

### Unit 3 — Speak model exposure fold
- Stop exposing overlapping Speak names (project_write_file, project_read_file,
  project_list_files, shell_run) on engine_tool_schemas when familiar catalog is active
- Keep internal PHASE4 / Control actions working for UI and adapters
- control.invoke: remove from model catalog unless a check proves an Iris-only escape still needs it

### Unit 4 — web + non-overlap
- Assert web_search/web_extract still on catalog (upstream OK)
- Assert non-overlapping toolsets not stripped by Unit 1
- Do not invent Speak web stack

### Unit 5 — Nudge shrink
- Remove / shorten MEMORY rules that say "use SpeakTools shell.run / do not use terminal"
  once terminal is Iris-backed familiar name
- Keep wiki/ide/diagram/app product teaching
- Bump nudge version marker; sync check green

### Unit 6 — :8642 residue purge
- Defaults, IDE hero pill, settings copy, setup strings, client fallbacks: no product
  implication of HTTP :8642 gateway
- Product ops still must not call ensure/restart gateway (existing _check_no_product_gateway_ops)
- Add/extend string scrape check for user-facing :8642 (tests may keep fixtures if labeled)

## Verification (main re-runs — every unit)
- That unit's new/updated checks green (fail→pass log)
- Per-unit live Iris smoke green (gate above); evidence under
  `.iris_light_test_tmp/verify-iris/<run_id>/` when using verify-iris
- Cross-cutting when relevant:
  - `.venv\\Scripts\\python.exe -m iris.engine._check_sidecar_disables_hermes_file_terminal`
    (update: Iris-backed familiar, not empty disable-only)
  - `.venv\\Scripts\\python.exe -m iris.system._check_no_product_gateway_ops`
  - `.venv\\Scripts\\python.exe -m iris.system._check_agent_surface_inventory`
  - chat landing: `_check_chat_landing_contract` / `_check_sidecar_done_landing`

## Out of scope
- Qt in-process AIAgent merge
- Renaming entire pin away from Nous in one PR
- Deleting all hermes_* shims (separate branding PR)
- Rebuilding Speak web search
- Skipping the per-unit Iris smoke gate to "go faster"

## Reply format
- Goal restated
- Principles used (Laziness, Fix Root Causes, Model the Domain, Experience First, Prove It Works, Sequence Verifiable Units)
- Per-unit: files, failing→passing check evidence, **live smoke result** (pass / bugfix PR URL)
- What was deliberately skipped
```

## 새 채팅에서 붙일 한 줄

`/poteto-mode` + 이 파일 첨부.  
「Unit 0부터 TDD. 매 Unit 후 Iris 재시작·실기동 스모크. 깨지면 버그픽스 PR로 고친 뒤에만 다음 Unit. file/terminal=익숙한 이름+Iris, web=Hermes 유지, :8642 잔재 청소. Phase1 Merge 금지.」
