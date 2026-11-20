# Prompt: familiar / Speak / fold → 헷갈리지 않는 이름 (동작 동일)

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-11-19 |
| 관련 | 흡수 완료 후 개발자 용어 혼동, fold=모델 노출만 숨김 |
| 대상 | `familiar_tools` · `speak_capability` · fold 표 · 관련 `_check_*` · nudge/주석의 개발자 용어 |
| 목적 | 층을 유지한 채 이름만 바꿔 읽히게 함. 모델 메뉴·Control 실행·grant 동작은 동일 |

```text
/poteto-mode

## Goal
Rename developer-facing concepts so the three layers read clearly:

  model_names     (was familiar)     — short names the model calls
  hide_from_model (was fold)         — overlap names omitted from model schemas
  tool_grants     (was SpeakGrant / Speak allowlist surface)

Behavior unchanged: same Control targets, same grants, same hide set, same
sidecar registration. No Hermes file/terminal re-enable. No gateway work.

## Domain shape (fixed)

Layers (do not collapse):
  model_names  →  Control action ids (local.*/project.*/shell.run/…)
  hide_from_model ⊆ Speak/engine schema names that duplicate model_names
  tool_grants  →  invoke permission + engine schemas (minus hide_from_model)

Suggested public names (adjust only if a collision is proven):
  iris/engine/familiar_tools.py
    → iris/engine/model_tool_names.py  (or keep filename one unit, rename types first)
  FAMILIAR_TOOLS → MODEL_TOOL_NAMES / MODEL_NAME_TO_CONTROL
  speak_names_hidden_when_familiar → names_hidden_from_model
  SpeakGrant → ToolGrant
  SpeakAllowlist / default_speak_tools → ToolAllowlist / default_agent_tools
  speak_capability.py → tool_capability.py (migrate imports same unit)
  User-facing nudge may still say “SpeakTools” if that string is product UX;
    prefer “Iris tools” / “agent tools” only where it does not break skills

## Why
- “familiar / Speak / fold” sound like three competing product systems
- They are one pipeline: alias → hide overlap → grant → Control
- Operator confusion; model never sees these words

## Constraints
- Laziness: rename + migrate callers + delete old names in the same unit
- No long-lived aliases (except one release if a public import is proven external — default: no alias)
- Do not expand hide_from_model set in this prompt (fold-extension is a later Feature)
- Do not delete Control actions or grants
- Do not change disabled_toolsets / web keep
- Fresh poteto-agent per unit; main re-runs checks
- Korean summaries; commit only if user asks

## Unit 1 — hide_from_model (fold rename only)

Rename fold table APIs and check module titles to hide_from_model.
Keep the same key set (project_write_file, shell_run, …).

Checks:
  .venv\Scripts\python.exe -m iris.engine._check_familiar_speak_fold
    (rename module to _check_hide_from_model if touched; update imports)
  assert hide set identical before/after (froze expected names in check)

Live smoke: none required if pure rename + checks green

## Unit 2 — model_names (familiar rename)

Rename familiar_tools domain table and sidecar load helper references.
Keep write_file/read_file/search_files/terminal → Control mapping identical.

Checks:
  _check_familiar_tools → _check_model_tool_names (or update in place)
  _check_familiar_tools_sidecar_load
  _check_familiar_surface_dispatch
  _check_sidecar_disables_hermes_file_terminal

Live smoke:
  Restart Iris → one turn that uses write_file or terminal still works

## Unit 3 — tool_grants (Speak* developer API rename)

Rename SpeakGrant / allowlist / speak_capability module paths used by sidecar
and checks. Product string “SpeakTools” in nudge: change only if Unit 0 note
says UX rebrand; default keep user-visible SpeakTools label OR switch to
“Iris tools” consistently in MEMORY nudge only — pick one in unit report.

Checks:
  _check_speak_tools_phase4
  _check_control_invoke_speak
  _check_engine_speak_tools_unit3
  engine_tool_schemas() names unchanged (except already-hidden set)

Live smoke:
  One chat turn LAND_OK; get_state or wiki tool still invokable

## Unit 4 — docs / comments sweep

Update code-review leftovers and prompt cross-links to the new terms.
Do not rewrite absorb history; add one “renamed to” line where needed.

Checks: grep for stale familiar_tools / SpeakGrant in iris/** (allow completed docs)

## Done when
- Old developer names gone from iris/ runtime imports (or listed exceptions)
- Hide set, model short names, Control targets byte-identical in behavior
- Main verified unit checks + live smokes
- Setup/gateway prompt remains separate; this prompt does not touch gateway

## Evidence
- Before/after hide-set dump (sorted names)
- Check command outputs
- One LAND_OK path
```

## 메인 메모

1. “모델 노출만 삭제”와 fold는 같은 층이다. 이 프롬프트는 그 층을 `hide_from_model`로만 부른다.
2. fold **확장**(project_run 등 추가 숨김)은 여기 넣지 않는다. 원하면 별도 1-unit Feature.
3. setup/gateway 프롬프트와 병렬 가능하나, 공유 파일 충돌 시 setup 먼저 또는 rename 먼저 직렬화.
