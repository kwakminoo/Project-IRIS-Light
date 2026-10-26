# Cross-judge. Browser agent arena

Candidate-1 is a generation-stamped PageIndex plus an extract verb.
Candidate-2 is a PageView with capped prose on every snapshot and no extract.

A future maintainer who opens one file must not break the rest. Depth and extendability beat line count.

## Scores

| Criterion | candidate-1 | candidate-2 |
|---|---|---|
| 1. Hermes `iris_invoke` is the only planner. No Python `Agent.run`. No Playwright process. | 5 | 5 |
| 2. After every act, Hermes can read enough to click and cite body. Page strings wrapped. Mid-loop JSON must not dump unwrapped title or body next to `ok`. | 4 | 3 |
| 3. `classify_turn` news cannot be stolen by SerpAPI `today_search`. Weather can stay a facts search. | 5 | 5 |
| 4. `command_specs()` is the one verb list. Teaching and SKILL derive from it. No regex intercept. | 5 | 5 |
| 5. Local-model token budget. Cap body. No screenshots by default. Extra verbs and extra round-trips count against this. | 4 | 3 |
| 6. HUD for send/purchase. Click/type wait for navigation inside execute. Stale locators fail closed. One targeting channel taught to Hermes. | 5 | 3 |

Totals. candidate-1 28. candidate-2 24. Max 30.

## Recommended base

**candidate-1.**

The packer is the only Hermes read of the page. Turn-start POST and mid-loop tool JSON both call `pack_hermes_result`. Title, names, excerpt, and extract body stay inside `BEGIN PAGE TEXT`. That closes the leak grounding already measured in `BrowserResult.to_control_dict()`.

Click and type parse as `ByRef` only. Refs embed generation (`g4e3`). After a settle the gen moves, so a copied id cannot silently hit a new node. That is the invariant a maintainer can keep by editing `session.py` stamp and resolve in one place.

`TurnKind.BROWSE` vs `FACTS` is an enum. News never sets `search_today`. Weather stays a facts search.

The extra extract verb is a real cost on criterion 5. It is still the right budget split. Snapshot stays an 800-character excerpt so a local model can pick a ref. Body at 4000, max 8000, is opt-in. Adding a later iframe or sidecar ref scheme can reuse the same `PageNode` and packer. Candidate-2's smaller verb list does not compensate for unwrapped mid-loop JSON and `n3` reuse across views.

## Grafts from candidate-2

Take two. Do not paste the rest.

1. **Viewport-first node ranking.** Rank visible nodes, then nodes inside `article` or `main`, then document order. Google and Naver put chrome links first. Candidate-1 keeps a document-order selector list. Without this graft the 40-node cap still hides headlines, so Hermes cannot choose a click even with refs.

2. **Typed `command_recipes()` with a per-recipe success field.** News and paper success is PAGE TEXT plus trusted url. YouTube success is `media.playing` only on that recipe. Candidate-1 already says this in teaching comments. A `Recipe` row in `command_specs()`'s teaching path makes a maintainer set success when they add a recipe, instead of leaving a global "success is playing" line.

Optional later, not a graft this round. Candidate-2 HUD scan of the resolved node name. Candidate-1 HUD already gates send/purchase. Add the name scan only if a live buy-button click misses the token list.

## Red flags

### candidate-1

- **Mild temporal split.** Hermes must search, click, then extract to cite a paper. That is the MCP loop, not a second planner. It still grows the public verb list by one. `scope=article|document` names a read stage.
- **Mild split of GUI vs Hermes dicts.** `to_gui_dict` / `iris_get_state` still expose title as chrome. Teaching must keep Hermes on `page_text`. A maintainer who packs `get_state` into the model restores today's mix.
- **Broad browse regex.** `_BROWSE` includes `유튜브`, `네이버`, `켜줘`, `열어줘`. "코드를 열어줘" can classify as browse. The news steal still stops. Tighten tokens to news and papers, same as candidate-2, when implementing.
- **Python/JS cap drift.** `NODE_CAP` lives in types and again in the bridge. Same risk on both candidates.

No second click language on the wire. No `Agent.run`. No Playwright process. No `wait` verb. Landmark is deleted, not kept beside `PageNode`.

### candidate-2

- **Split ownership of what Hermes sees.** Call site 1 returns `BrowserResult.to_control_dict()` with `nodes`, `prose`, `href` next to `ok`. The packer also wraps PAGE TEXT. Two formatters. Editing one file does not update the other. This is the HEAD leak, redrawn.
- **Two ways to click.** `Locator` stays `ByCss | ByText | ByRole | ByRef`. Parse keeps old branches for "old callers". Teaching lists `by=ref`. A maintainer copies the first parse branch they find.
- **Stale locators do not fail closed.** Refs are `n0`..`n39` with `view_seq` on the snapshot, not in the ref. After navigation the next page also has `n3`. Execute succeeds on a different node. Candidate-2 rejected integer indexes for this reason, then shipped the same identity.
- **Shallow public locator.** Callers still choose `by`. Capability that should sit in execute leaks into the wire dict.
- **Token dump.** 2500 characters of prose plus href and bbox on every act, including YouTube and Google results. `prose_truncated` in the trusted block is fine. Unwrapped `prose` in `to_control_dict` is not.
- **Hand-synced settle budget.** Click waits 12s. Navigate waits 45s on HEAD. Two timeouts for one load.

No `Agent.run`. No Playwright process. No extract verb. No regex intercept. `command_recipes()` itself is not a red flag if `control_names` must be specs.

## Criterion notes

1. Both keep `iris_invoke` → `_handle` → `execute`. Both refuse a Python loop and a sidecar unless the live ten-utterance predicate fails. Tie.

2. Candidate-1 wrap is correct. Cite of a full article needs extract, so not a 5. Candidate-2 has body after every act, then undoes it by dumping unwrapped nodes and prose beside `ok`. Wrap is the load-bearing sentence.

3. Both send news to browse and keep weather on facts/today. Both assert the 22:47 utterances. Tie. Candidate-1 enum is cleaner. Candidate-2 browse regex is tighter. Neither loses the steal.

4. Both derive teaching and SKILL from `command_specs()` and keep intercept gone. `_check_intent.py` fails on drift. Tie.

5. Candidate-1 pays an extra verb and an extra round-trip on papers. Default path stays small. Candidate-2 pays 2500 tokens on every snapshot and still needs scroll plus another snapshot for long papers. No screenshots in either.

6. Candidate-1 settle shares the navigate `loadFinished` family, stale gen fails closed, wire click is ref only, HUD ignores `args.confirm`. Candidate-2 settle exists, HUD can scan the node name, then loses fail-closed identity and keeps three extra locator branches.
