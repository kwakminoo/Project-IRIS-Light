# Phase A grounding — Iris chat code/shell cards → Cursor parity

## Goal (user)

Make Iris chat code boxes and shell boxes feel and behave like Cursor's.

## What exists today (verified in prior session + code)

- `FencedCodeBlock(code, language)` → table card: language left, 「복사」 right (`iris-copy://`), Pygments body.
- `ToolShellBlock(title, command, output, status, block_id, collapsed)` → collapsible `>_` card (`iris-collapse://`).
- Markdown path: `render_*` → `_upgrade_fenced_pre_to_cards` uses language class only.
- Streaming path: `chat_block_parser` puts fence info string wholesale into `language`.
- Shell visibility: `run_visibility` clips command~240 / output~400; post-hoc card, not live approve UI.
- Qt constraint: padding/border need `<table>` for code cards; shell still uses `<pre>`.

## Cursor gaps that matter to users (Experience First order)

1. Code header shows **filepath** when known (not only language).
2. Code card can **open the file** (Iris already has `iris-file://` chips).
3. Shell card has **Copy command**, clearer status, expandable body that looks like a terminal tool card.
4. Out of scope for this slice: Ask-mode Apply, live Shell approve/sandbox UI, unbounded stdout dump, Explored-N grouping.

## Constraints

- Keep Qt Rich Text HTML approach (no React rewrite).
- Extend existing `chat_blocks` types or one thin parser helper. Do not invent a parallel card system.
- Tests: `python -m iris.ui.chat._check_chat_blocks` must keep passing and grow asserts.
- Comment policy: only non-obvious why. Korean comments match file.

## Data shape name (parent)

Domain model: **ChatCard** variants already exist as `FencedCodeBlock` / `ToolShellBlock`. Enrich those frozen dataclasses. Fence meta parsing is a pure function at the markdown/stream boundary.
