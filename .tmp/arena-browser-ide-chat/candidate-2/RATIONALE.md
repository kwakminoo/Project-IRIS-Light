# Rationale. Whole-merge, then restore dedicated left mount

## Problem

Dedicated browser already uses the same `ChatPanel` instance as IDE companion. The gap is the class. origin/main shipped presenting/stop, wiki quote strip, GPT fences, `exec_python`, and DragTab TTS. Committed `serin` did not. Getting that class onto the shared instance is non-obvious because ChatPanel is not one file, `main_window.py` both wires those features and hosts dedicated enter, and origin/main's `IdeUnifiedShell` has no `mount_left_browser`. The user forbade a blind merge (wiki/email/obsidian), and the working tree holds uncommitted silero/model_prefs plus a dirty ChatPanel subgraph that already matches origin/main.

## Usage (caller's view)

Screens keep calling `show_browser_workspace()`. They do not choose a ChatPanel. The implementer runs one transition. Park silero without editing it. Park dirty paths that overlap the merge. `git merge origin/main`. Restore `mount_left_browser` and dedicated enter if the four conflict files dropped them. Pop the stashes. After that, dedicated remounts `self._chat` as today, and that widget is origin/main's class. IDE-internal stay on `IrisIdeWindow._stack`. Types in DESIGN.md follow this sequence.

## Shape

Working tree phases are the domain model (model-the-domain). `Dirty → Parked → Merged → OccupancyRestored → SileroRestored`. Chat identity stays one instance on `MainWindow`. Left occupancy stays three occupants on one `IdeUnifiedShell` (HWND, BrowserPanel, workspace content). Restore is the three occupancy methods plus dedicated enter, not a new shell (laziness-protocol). Interface depth. `show_browser_workspace()` hides the ChatPanel closure and the merge. Conflict policy is occupancy-first on `ide_companion_page.py` and hunk-level on `main_window.py`. Validation at the git boundary. `_check_browser_workspace` after restore. Silero files are never a merge input. Deliberately not done. A second ChatPanel, `mount_workspace` for the browser, or a product `LeftOccupant` enum.

## Synthesis decision

Candidate only. Arena fills this after comparing packages. This runner's candidate is whole-merge plus occupancy restore, not a file-port.

## Tradeoffs accepted

- We accept origin/main's wiki/email/obsidian rewrite (76 files, 6583 insertions since merge-base, measured) in exchange for git enumerating ChatPanel callers instead of a hand-synced copy list.
- We accept four committed conflict files (`main_window.py`, `ide_companion_page.py`, `hosts.py`, `hermes_memory_nudge.py`, measured via `merge-tree`) in exchange for 3-way context on the file that both adds presenting and hosts dedicated enter.
- We accept a mandatory occupancy restore in exchange for not treating main's `IdeUnifiedShell` as a newer replacement of serin's occupant API.
- We accept named stashes in exchange for not touching silero/model_prefs content.
- We accept a larger-than-necessary tree diff relative to "same ChatPanel instance" in exchange for one revision across ChatPanel and `main_window.py` send-path hunks.

## Alternatives considered

- **File-port.** Copy ChatPanel and its import closure onto `serin`. No `git merge`. Occupancy never deleted. Interface stays `show_browser_workspace()`. Exposes a hand-synced file list and leaves `main_window.py` send-path hunks to a second splice that is the merge conflict without git. Already mostly done in the working tree (those files match origin/main, measured). Wins when the operator's forbid and laziness-protocol dominate. Loses when completeness of window wiring is the actual gap.
- **Merge with ours on the two occupancy files.** Occupancy survives. Chat class and window wiring can diverge. Split ownership of one send-path. Rejected.
- **Reuse `mount_workspace` for BrowserPanel instead of restore.** One mount name, two occupants collapsed. Rejected.

## Open questions and risks

- Does the operator still forbid this merge after seeing that ChatPanel's origin/main imports pull wiki widgets and that a whole merge cannot leave email/obsidian behind?
- Should dirty files that already equal origin/main be dropped before merge, or is popping them after restore a self-conflict?
- Can dedicated enter and main's `resizeEvent` ratio re-apply both run without fighting the 80:20 split?
- Are the `hosts.py` / `hermes_memory_nudge.py` conflicts load-bearing for Hermes `browser.*`, or noise next to occupancy?

## Next implementation step

Do not merge in this pass. If synthesis picks this shape, start with the silero named stash and a `merge-tree` re-check, then merge and restore occupancy from the conflict policy in DESIGN.md.
