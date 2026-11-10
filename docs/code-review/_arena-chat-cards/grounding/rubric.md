# Arena rubric — Cursor-parity chat cards

Artifact each candidate produces: one DESIGN.md (usage + type sketch + rationale).

## Criteria (score 1–5 each)

1. **Usage-first fidelity.** Call sites match how Iris actually renders (renderer, streaming parser, insert_tool_shell) without inventing a second public path.
2. **Domain encoding.** Fence meta (lang / path / line range) and shell display fields live in a structure, not scattered string splits in HTML.
3. **Qt honesty.** Design respects QTextEdit Rich Text limits (table cards, custom schemes) instead of assuming web CSS.
4. **Interface depth.** Callers change little; complexity of Cursor-like header/actions hides behind existing HTML entry points.
5. **Laziness / shippable slice.** No Apply, no live approve, no new widget stack unless it clearly earns its keep for this UX gap.
6. **Extensibility without two ways.** One way to build a code card and one way to build a shell card after the change.
