# Prompt: Iris Agent setup·gateway 잔재 (툴 카탈로그 제외)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-19 |
| 관련 | `docs/code-review/completed/Iris-Agent-툴셋흡수-완료-Hermes잔재-2026-11-19.md`, InternalSidecar-only, `_check_no_product_gateway_ops` |
| 대상 | setup `agent_runtime` probe · `iris_agent_gateway` 존속/삭제 · 브랜딩 API 심볼 · env `:8642` |
| 목적 | 제품 설치·진단이 sidecar 의미와 맞게 정렬. 채팅 툴 카탈로그·familiar·Speak fold는 건드리지 않음 |

선행 계약 (깨면 회귀).

- 제품 채팅 = InternalSidecar only. Qt same-process AIAgent merge 금지 (Phase1 NO-GO).
- 제품 경로에서 `:8642` gateway start/restart 금지 (`_check_no_product_gateway_ops` green 유지).
- thin `dist/IRIS.exe` · no-console-windows · hermes-chat-landing · qt-slot-abort.

```text
/poteto-mode

## Goal
Align setup/install diagnostics with InternalSidecar. Stop implying that product
runtime readiness means “HTTP gateway can start”. Decide whether
`iris_agent_gateway.py` stays as opt-in diagnostics or is deleted. If deleted,
skip a rename-only wave. Do not change familiar/Speak/tool catalog in this prompt.

## Out of scope (hard)
- familiar_tools / Speak fold / disabled_toolsets file|terminal policy
- Merging tools into Hermes file/terminal toolsets
- MEMORY nudge tool sermons (except labels that say “gateway” as product chat path)
- Qt in-process AIAgent merge
- Commit/PR unless the user asks

## Domain shape (fixed)

Product readiness (must become true):
  agent venv python exists
  sidecar can import agent runtime deps needed for InternalSidecar turns
  home + provider config ready
  SpeakTools posture verify (get_state / get_catalog / control.invoke) OK
  agent_base_url == "" on product path

Opt-in gateway (optional leftover — decide Keep or Delete in Unit 0):
  IRIS_AGENT_BASE_URL non-empty → may probe /health on that URL
  Never seeded by product setup/env defaults
  Never started by product chat sync (reconnect_gateway stays False)

Probe meaning (replace gateway-centric wording):
  Today: probe_hermes_runtime ≈ “can this venv start gateway (hermes_cli+aiohttp+…)”
  Target: probe_agent_runtime / probe_sidecar_runtime ≈
    “can this checkout run InternalSidecar agent turns”
  If Keep gateway module: gateway-specific health stays behind opt-in URL only
  If Delete gateway module: no start/restart/ensure_*_gateway; health only N/A

## Why
- Absorption + branding already moved chat off :8642, but setup still calls
  probe_hermes_runtime and gateway-shaped helpers for “agent_runtime”
- Users see “runtime ready” language that still smells like gateway
- Rename-only of gateway APIs is wasted if the module will be deleted next

## Constraints
- Laziness Protocol: smallest change that makes setup meaning true
- Migrate callers then delete legacy names in the same unit (no long-lived aliases)
- Fresh poteto-agent per unit; main re-runs checks
- Korean summaries
- Gate: Unit N green (checks + required live smoke) before Unit N+1

## Unit 0 — Decision record (no large code)

Write a short decision into the unit report (and optionally one paragraph in
docs/code-review/ completed later):

  Keep | Delete  for iris_agent_gateway product surface

Keep if:
  - install/setup still need a shared process-tree killer / orphan prune that
    only lives in that module, AND no cheaper sidecar-only substitute exists yet
Delete if:
  - every product caller can use ensure_iris_agent_runtime(start_gateway=False)
    + a sidecar import probe, AND opt-in :8642 is unused on this machine/CI

Also list remaining hermes_* public symbols that are setup/gateway-only
(not tool catalog). Do not rename yet.

Checks:
  - Decision is written; Keep XOR Delete chosen
  - Out of scope tools unchanged (git diff has no familiar_tools / speak fold edits)

Live smoke: none

## Unit 1 — Setup probe = sidecar meaning

Change `_step_agent_runtime` / install auto-repair so the primary probe answers
“sidecar runtime OK”, not “gateway can bind :8642”.

Required behavior:
  - start_gateway=False stays
  - product agent_base_url empty stays
  - broken venv / missing hermes_cli / trampoline still auto-repair once
  - success summary must not tell the user that gateway is the chat path
  - if Keep: gateway start APIs remain importable but not called from product setup
  - if Delete: product setup must not import start/restart/ensure_*_gateway

Rename in this unit only if it reduces confusion for the probe entrypoint
(e.g. probe_hermes_runtime → probe_agent_runtime) AND all callers+checks move
in the same unit. Do not rename the whole gateway module yet if Keep.

Checks (add/adjust as needed):
  .venv\Scripts\python.exe -m iris.system._check_no_product_gateway_ops
  .venv\Scripts\python.exe -m iris.system._check_gateway_setup_step
    (rewrite expectations: product step must not start gateway;
     if Delete, mark obsolete or replace with sidecar probe check)
  New or updated: _check_agent_runtime_probe_sidecar (or extend setup check)
    - assert product setup path never calls ensure/restart/start_*gateway
    - assert probe failure strings used for repair are sidecar-relevant

Live smoke:
  - Run setup agent_runtime step (or dry equivalent) on a healthy install
  - Confirm summary mentions sidecar / SpeakTools, not “gateway listening :8642”
  - One chat turn still lands assistant (verify-iris or manual)

## Unit 2 — Gateway Keep cleanup OR Delete

### If Keep
  - Opt-in only: health/API_KEY messages already say “opt-in gateway”
  - Ensure workspace .env / .env.example do not re-seed :8642
  - load_settings product path ignores legacy IRIS_HERMES_BASE_URL=:8642 for chat
    (or maps empty); do not force-delete user env files
  - Public API rename wave ONLY if Unit 0 said Keep-and-rename:
      restart_hermes_gateway → restart_agent_gateway (etc.)
      migrate all callers + _check_* + short doc note in one unit
  - If Unit 0 said Keep-but-defer-rename: stop after env/setup label cleanup

### If Delete
  - Remove product imports of start/restart/ensure_*gateway
  - Delete or gut iris_agent_gateway lifecycle that only serves :8642
    (keep tiny helpers only if install still needs them — prefer move to
     iris_agent_install / agent_runtime first)
  - Update _check_no_product_gateway_ops to assert absence or zero imports
  - Skip rename-only wave entirely
  - Docs: one paragraph that product diagnostics are sidecar-only

Checks:
  _check_no_product_gateway_ops
  _check_no_user_facing_8642 (or equivalent)
  settings load: agent_base_url empty on product defaults
  grep product globs: no ensure_hermes_gateway_running / restart_hermes_gateway
    outside exempt diagnostic stubs (Delete → none)

Live smoke:
  - Iris start → one chat turn LAND_OK
  - Setup agent_runtime still completes on healthy machine
  - If Delete: setting empty base URL does not try to open :8642

## Unit 3 — Branding leftovers that are NOT tools

Only symbols/labels that confuse setup/UI with Hermes-as-product-chat:

  Candidates (confirm against tree; skip if already gone):
  - hermes_update / load_hermes_tool_choice product labels
  - setup wizard copy that says gateway is the chat path
  - hero/status strings still implying :8642 for product
  - agent_command fallbacks still "hermes" in setup-only paths

Do not rename pin vendor paths, NOTICE licenses, or upstream package names.

Checks:
  targeted _check_* for renamed entrypoints
  _check_no_user_facing_8642
  no familiar/Speak catalog diff

Live smoke:
  - Open setup wizard: labels say Iris Agent / sidecar
  - One chat turn OK

## Done when
- Unit 0 decision recorded
- Product setup probe means sidecar readiness
- Keep: opt-in gateway cannot be re-seeded by product defaults; rename done or explicitly deferred
- Delete: no product gateway lifecycle; rename skipped
- Tool catalog files untouched by this prompt’s units
- Main verified checks + live smokes; evidence paths listed in the final report

## Evidence to collect
- Command outputs for each unit’s checks
- Decision Keep|Delete one-liner
- Live: setup summary text + one LAND_OK path under .iris_light_test_tmp if used
```

## 메인 조율 메모

1. 이 프롬프트는 **툴 병합/familiar/Speak 재설계와 분리**한다. 툴 쪽은 별도 Feature·별도 프롬프트.
2. Unit 0에서 Delete가 나오면 Unit 2는 삭제만. rename 파도를 중간에 끼우지 않는다.
3. `probe_hermes_runtime`의 aiohttp 검사는 gateway 잔상이다. sidecar-only면 “턴에 필요한 import 집합”으로 재정의하는 편이 맞다. 집합은 측정 후 최소로.
4. 완료 후 이 파일과 짝 보고서는 `docs/prompts/completed/`, `docs/code-review/completed/`로 옮긴다.
