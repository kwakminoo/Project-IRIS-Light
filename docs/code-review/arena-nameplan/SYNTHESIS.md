# NamePlan synthesis

## Synthesis decision

Base: Candidate 1 ([NamePlan design A](0b9405ba-f895-4f45-820e-584b8f04a243)). Cross-judge ([cross-judge](649b2e1f-01eb-44fd-8cfc-f095cec8d000)) 23 vs 21 agrees.

Public entry: `resolve_create_rel_path` re-exported from `iris/ui/chat/file_write_claim.py`. Implementation may live in `iris/ui/chat/name_plan.py` if the claim file stays thin.

## Grafts from Candidate 2

1. Nameless + multiple fences → `skip` (not ask). Named N≠M mismatch ask stays.
2. Path freeze: open uses goal+lang(+explicit names) only. Later fence body does not re-invent the stem. Code hints only when no frozen open path and single end-of-turn resolve.

## Rejected

WriteBatch / LocalWritePlan deletion. NewType RelPath. Dual public destination/batch API. Forever shim.

## Phase C done when

- Vibe trio and dead `_write_fenced_once` call `resolve_create_rel_path` (or claim re-export).
- `default_generated_rel_path` deleted; no imports.
- Nameless single-fence plan → write English path (tests updated in C so suite stays green).
- Nameless multi-fence → skip.
- `RelPath.parse` rejects `iris_generated.*` for explicit zip too.
- Assert: same goal+lang → vibe open rel equals plan pair path when plan is write.
