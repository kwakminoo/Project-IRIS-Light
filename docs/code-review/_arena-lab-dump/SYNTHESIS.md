# Synthesis — chip PDF lab-script dump

## Base

**Candidate A** (app-owned intercept). Matches locked policy and how intercept: skip AttachmentWorker/Hermes stuffing when intent matches; fixed short reply with paths.

## Grafts from B

1. `LabDumpSummary` / `to_hermes_summary` — bodies never cross model boundary (types encode it).
2. `content.dump_lab_scripts` control action — Hermes fallback / MCP when preflight missed.
3. Nudge 15h — force dump tool; forbid full `content.extract` refill for this intent.

## Rejected

- Raising or removing `MAX_CONTEXT_CHARS` / file-byte caps.
- Hermes-only path without app preflight (still fails when model ignores tools).
- Putting `LabProgram.body` into chat history or tool results.

## Contract for implementer

| Piece | Path |
|---|---|
| Pure dump | `iris/knowledge/lab_script_dump.py` |
| Intent (can live in same module) | `is_lab_dump_intent`, `pdf_paths_from` / `pick_pdf_source` |
| Worker | `iris/ui/workers/lab_dump_worker.py` |
| Hook | `MainWindow._try_local_lab_dump` before AttachmentWorker (like `_try_local_pdf_save`) |
| Action | `content.dump_lab_scripts` next to `content.extract` in `control_actions/wiki.py` or sibling |
| Check | `iris/ui/_check_lab_script_dump.py` — intent, parse labels→filename, dump hybrid PDF writes files, reply has no page bodies |
| Limits | keep 20MB / 24k / 200 pages / vision 4 / extract 80k |

Default out dir: `labs/`. Idempotent overwrite same path.
