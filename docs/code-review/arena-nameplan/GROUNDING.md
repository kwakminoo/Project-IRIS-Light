# NamePlan grounding (Feature)

Source: how pass [how NamePlan](c39f440c-c021-4aca-ab83-2c4342ade272).

## Three name paths today

1. VerifyTurn → `plan_local_file_writes` in `iris/ui/chat/file_write_claim.py` (named paths only; ask if unclear; bans `iris_generated.py`).
2. Live vibe code still calls `default_generated_rel_path` → `iris_generated.*` in `_live_vibe_open_target`, `_try_reveal_local_vibe_code`, dead `_write_fenced_once`. Gated off by empty `_pending_local_vibe_prompt` each turn.
3. Hermes nudge text only: ask if unnamed; no shared Python NamePlan.

## Where shared resolve must live

`iris/ui/chat/file_write_claim.py`. Vibe open/reveal and VerifyTurn both call it. Do not put policy in `default_generated_rel_path`.

## Locked product (operator)

- Remove rule-based ask for nameless create.
- English filenames even if user spoke Korean.
- Infer name from code/goal and write immediately.
- Unify vibe onto same plan; delete `default_generated_rel_path` after migrating callers.
- Phases C → A → B.
