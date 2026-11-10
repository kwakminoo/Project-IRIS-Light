# Synthesis — Cursor-parity chat cards

## Recommended base

**Candidate A (enrich-in-place).**

Parent and cross-judge agree. Same public HTML entry points, one `parse_fence_info`, fields on existing frozen blocks. B's view-model modules open a second paint path for this UX gap.

## Scores (parent / judge)

| Criterion | A | B |
|---|---|---|
| Usage-first fidelity | 5 / 5 | 4 / 3 |
| Domain encoding | 5 / 5 | 5 / 4 |
| Qt honesty | 5 / 5 | 5 / 5 |
| Interface depth | 5 / 4 | 3 / 4 |
| Laziness / shippable | 5 / 5 | 2 / 2 |
| One way | 5 / 5 | 4 / 3 |
| Judge total | 29 | 21 |

## Grafts from B

1. Code header: path as **primary**, language as muted **secondary** when both exist.
2. Shell status: normalize to kind + short label in HTML (성공/실패), without new wire fields.
3. Keep facades-only discipline: product code must not grow a second HTML builder.
4. Open-file grey-out stays off the block fields (HTML / file_chip policy only).

## Rejected

- `card_models.py` / `card_html.py` split for this slice
- Opaque wire `language` blob that only the adapter splits
- Apply button, live approve UI, RunVisibility clip changes

## Implementation contract

Follow candidate-a DESIGN.md Shape + grafts above. Next step: `FenceInfo` + `parse_fence_info` + checks, then headers, then shell chrome.
