# Synthesis — project.read_file

## Rubric scores (0-2)

| Criterion | A disk-only | B editor-first |
|---|---|---|
| Bound-workspace safety | 2 | 2 |
| Dual of write | 2 | 1 (adds bridge path) |
| Honesty | 2 (hard fail oversize/binary) | 2 (via/truncated) |
| Diff size | 2 | 0 (bridge+bundle sync) |
| Testability | 2 | 2 |
| No forbidden paths | 2 | 2 |
| **Total** | **12** | **9** |

## Base
Candidate A (disk-only UTF-8 dual of write).

## Cross-judge
Skipped: arena runners and parent are all `auto` / same family; Phase C requires another family.

## Graft from B
MEMORY nudge one honesty line: `project.read_file` is disk bytes; unsaved Monaco buffer is not claimed — save via `ide.save` or edit via `ide.edit` first when the tab is dirty.
Do **not** graft bridge `readBuffer` in v1 (Laziness Protocol).

## Rejected
B as base: larger surface, IDE rebuild rule, timeout/fallback complexity for the first fill of a missing primitive.
