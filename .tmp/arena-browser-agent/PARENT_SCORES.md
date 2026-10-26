# Parent scores (before cross-judge)

Rubric 0-5. Criteria from the arena frame.

| Criterion | C1 PageIndex+extract | C2 PageView+prose |
|---|---|---|
| 1 Planner stays Hermes, no Playwright | 5 | 5 |
| 2 Read after act, untrusted wrap, no leak in tool JSON | 5 | 3 |
| 3 News not stolen by SerpAPI | 5 | 5 |
| 4 One verb list, teaching derived, no regex | 4 | 5 |
| 5 Local-model tokens | 4 | 3 |
| 6 HUD, settle, stale fail-closed, one taught click channel | 5 | 4 |
| **Total** | **28** | **25** |

## Notes

C1 wins criterion 2 because `pack_hermes_result` is the only Hermes read. C2 still returns unwrapped `prose` and node names in `to_control_dict`.

C1 wins tokens on search pages (800 excerpt, extract only when asked). It spends an extra MCP round for every article.

C2 wins verb-list simplicity. Playwright MCP also has no extract tool. Reading is the snapshot.

C1 refs embed gen (`g4e3`). C2 refs (`n3`) can collide after a new snapshot.

C1 `Click.target: ByRef` only on the command type. C2 keeps `Locator` union including CSS on the wire parse. Teaching lists only ref. Two ways still exist in `parse_command`.

## Lean

Base C2 if we graft C1's packer-as-boundary and gen-stamped refs. Public surface stays small. Tool JSON stops leaking page strings. Stale clicks fail closed.

Base C1 if the extra extract verb is cheaper than 2500 chars on every YouTube and Google results page. That is the token bet.

Interface depth favors C2 plus those two grafts. A maintainer adding a verb still touches `command_specs()` only. They do not learn extract vs snapshot staging.

Disagreement with a judge that picks raw C1 without grafting the packer into C2, or raw C2 without the packer, means the rubric on criterion 2 was underspecified.
