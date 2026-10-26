# DESIGN. Whole-merge origin/main, then restore left occupancy

## Problem

Dedicated browser already remounts the single `MainWindow._chat` onto `IdeCompanionPage` and puts `BrowserPanel` on `IdeUnifiedShell` via `mount_left_browser`. IDE-internal browser stays on `IrisIdeWindow._stack`. Chat behavior on dedicated is therefore whatever the `ChatPanel` class is, not a second composer.

Committed `serin` (`7ec6656`) does not ship origin/main's ChatPanel. origin/main (`74c1a19`) adds wiki quote strip, `_presenting` / `set_presenting` / `is_typing_active`, GPT matrix fences (`gpt_answer_contract`), `chat.exec_python`, and DragTab header TTS. Those features live on the class and on its send-path callers in `main_window.py`. They do not live on the dedicated-enter function.

This candidate integrates that class by merging `origin/main` into `serin`, then putting occupancy back if the merge drops it. It is the whole-tree shape. A file-port copies a ChatPanel closure by hand and never runs `git merge`.

Constraints from grounding, re-checked this session.

- Do not merge blindly. The user already forbade it because main rewrote wiki/email/obsidian.
- Do not edit `iris/audio/silero_vad.py`, `iris/storage/model_prefs.py`, or `tests/test_silero_vad.py`.
- Do not clone ChatPanel.
- Keep dedicated vs `ide_internal` separate.
- Keep `BrowserSession`, Hermes tool calling, and `mount_left_browser`.

Measured tree facts this session, not guesses.

- merge-base `ee099c2`.
- origin/main since merge-base. 76 files, 6583 insertions, 341 deletions.
- wiki/email/obsidian slice of that. 24 files, 2725 insertions, 151 deletions.
- email/obsidian pages plus email client/workers/tests. 6 files, 1132 insertions, 132 deletions.
- `git merge-tree --write-tree HEAD origin/main` conflicts in four committed paths. `iris/ui/window/main_window.py`, `iris/ui/workspaces/ide_companion_page.py`, `iris/ui/control_actions/hosts.py`, `iris/system/hermes_memory_nudge.py`.
- origin/main has `mount_workspace` and no `mount_left_browser` / `dedicated_browser`.
- origin/main does not touch the silero trio.
- Working tree already matches origin/main on `chat_panel.py`, `drag_tab.py`, `gpt_answer_contract.py`, `chat_code_exec.py`, `wiki_quote.py`, `wiki_study_widgets.py`. That is a file-port already sitting dirty. 19 dirty paths also appear in origin/main's delta.

## Usage (caller's view)

Nobody on a screen asks which ChatPanel to build. After this candidate lands, dedicated enter is the same remount it is today. The instance is still `self._chat`. The class is origin/main's.

**Later implementer (the only new caller).**

```python
# not product UI. One named transition. Do not improvise a second paste.
park = park_unrelated_dirty()          # silero trio, content byte-identical
overlap = park_merge_overlapping_dirty()  # dirty chat/wiki that git merge would clobber
result = merge_origin_main()           # git merge origin/main into serin
restore_left_occupancy(result)         # no-op if ours occupancy survived
restore_named_stashes(park, overlap)
```

**Dedicated open after that transition (unchanged public window API).**

```python
panel = window.show_browser_workspace()
assert window._ui_mode == "dedicated_browser"
assert window._body_stack.currentWidget() is window._unified_shell
assert window._unified_shell.left_browser() is panel
assert window._companion_page.is_mounted()
assert window._chat is window._companion_page._mounted[-1]
assert hasattr(window._chat, "set_presenting")
assert window._iris_ide_window is None or not window._iris_ide_window.isVisible()
```

**IDE-internal still a different occupant.**

```python
window._ui_mode = "ide_companion"
panel = window.show_browser_workspace()
assert window._ui_mode == "ide_companion"
assert window._unified_shell.left_browser() is None
assert ide.is_browser_visible() or ide._stack.currentWidget() is panel
```

**Typing on dedicated is typing on the IDE companion widget.**

```python
# DragTab TTS, wiki quote strip, stop-while-presenting, exec_python
# fire because _chat is that class, not because dedicated-enter grew a branch.
window._chat.set_presenting(True)
assert window._chat.is_typing_active()
```

Callers never pass a ChatPanel factory. `show_browser_workspace` does not grow a "use main chat" flag.

## Shape

**Chat identity is the instance, not the screen.** Per model-the-domain. `MainWindow` owns one `ChatPanel`. Screens remount it with `addWidget`. Dedicated chat after merge is origin/main's ChatPanel because the class of that instance changed, not because a second widget was built. A file-port tries to change the class by copying files. This candidate changes the class by moving `HEAD`.

**Left occupancy is a third fact, next to `_ui_mode` and `ViewHost`.** `IdeUnifiedShell` left pane is one of `HwndPlaceholder` (Theia), `BrowserPanel` (dedicated), or `WorkspaceContent` (`mount_workspace` for mail/calendar/wiki). origin/main encodes the first and the third. serin added the second as `mount_left_browser` / `left_browser` / `clear_left_browser`. Merge taking theirs on `ide_companion_page.py` makes `BrowserPanel` unrepresentable. Restore is not a new layout. It is putting that occupant back on the same shell. Per laziness-protocol the restore is those three methods plus `_show_dedicated_browser` / `_exit_dedicated_browser` if `main_window.py` resolution dropped them. No second `IdeUnifiedShell`. No occupancy protocol class.

**The merge is a state machine on the working tree, not a checklist in chat.** Phases are `Dirty`, `Parked`, `Merged`, `OccupancyRestored`, `SileroRestored`. Each phase has one owner and one check.

| Phase | Writes | Check |
| --- | --- | --- |
| Parked | named stashes only | silero files byte-identical to pre-park. merge-overlapping dirty paths unblocked. |
| Merged | git merge | four conflict paths exist as a finite set. wiki/email/obsidian from main are in the tree. |
| OccupancyRestored | occupancy methods and dedicated enter if missing | `_check_browser_workspace` observables. `left_browser() is panel`. |
| SileroRestored | stash pop of the silero trio | those three files match the park, not origin/main (main never touched them). |

Idempotent. Merge on an already-merged `serin` is a no-op. Restore on a shell that still has `mount_left_browser` is a no-op. Park of a clean silero trio is a no-op.

**Conflict policy is occupancy-first, not ours-or-theirs.** Measured four files.

- `ide_companion_page.py`. Keep `mount_left_browser` / `left_browser` / `clear_left_browser` and dedicated insets. Take main's `mount_workspace`, `COMPANION_CONTENT_RATIO`, `resizeEvent` ratio re-apply, hover handle if theirs is ahead. Those are one left host with three occupants, not two competing shells.
- `main_window.py`. Keep `_show_dedicated_browser`, `_exit_dedicated_browser`, `PanelHost(site="dedicated")`, and dedicated exits from home/mail/calendar/wiki. Take main's ChatPanel wiring (`typing_finished`, presenting, wiki quote, exec_python) and wiki/email/obsidian window hunks. This file is ~9500 lines on both sides. Resolving it as theirs deletes dedicated enter. Resolving it as ours drops main's send-path. The policy is hunk-level, one occupant API plus one ChatPanel class.
- `hosts.py` and `hermes_memory_nudge.py`. Unrelated to occupancy. Merge for compile. Do not use them as a reason to re-shape the shell.

**What the public surface hides.** `show_browser_workspace()` stays one name. Behind it, git has already replaced ChatPanel, DragTab TTS, `gpt_answer_contract`, `chat_code_exec`, and the wiki quote widgets ChatPanel imports. Callers do not list that closure. That is the depth argument against a file-port. ChatPanel on origin/main imports `iris.knowledge.wiki_quote` and `iris.ui.knowledge.wiki_study_widgets`. A copy of `chat_panel.py` alone does not import-check.

**What this candidate will not hide.** wiki/email/obsidian workspace pages land because they are on origin/main. 6583 insertions is the cost of using git as the closure. Per laziness-protocol that cost is not the smallest change for "dedicated uses the same ChatPanel". It is the smallest change for "ChatPanel and every main_window send-path hunk that references it are the same revision". Those are different problems. This candidate solves the second, and dedicated chat follows because the instance is shared.

**Call chain after land.** `browser.open` → `BrowserSession.execute` → `show_browser_workspace` → `_show_dedicated_browser` → `mount_left_browser` + companion already holding `_chat`. Three files. Chat features do not add a fourth coordinator.

**Shared writers.** Silero files and the merge must not share a write. Main does not touch them. Park them anyway so a dirty tree cannot block or mix the merge. Per separate-before-serializing, two actors (merge, silero work) do not serialize through the same paths. Restore the stash last so occupancy edits cannot mark those files.

**What this sketch refuses.**

- `git merge origin/main` with no occupancy restore.
- Resolving `ide_companion_page.py` as theirs because main's shell "looks newer".
- Cloning ChatPanel onto dedicated to "keep serin's chat".
- Re-hand-writing `_presenting` on serin's class after a merge that already brought it.
- Using `mount_workspace` for BrowserPanel.
- Editing silero/model_prefs as part of the merge.

## Types (derived from usage)

```python
from enum import Enum
from pathlib import Path
from typing import Literal

class WorkingTreePhase(Enum):
    DIRTY = "dirty"
    PARKED = "parked"
    MERGED = "merged"
    OCCUPANCY_RESTORED = "occupancy_restored"
    SILERO_RESTORED = "silero_restored"

class LeftOccupant(Enum):
    HWND_PLACEHOLDER = "hwnd"
    BROWSER_PANEL = "browser"
    WORKSPACE_CONTENT = "workspace"

SileroPaths = tuple[
    Literal["iris/audio/silero_vad.py"],
    Literal["iris/storage/model_prefs.py"],
    Literal["tests/test_silero_vad.py"],
]

CONFLICT_PATHS: tuple[Path, ...] = (
    Path("iris/ui/window/main_window.py"),
    Path("iris/ui/workspaces/ide_companion_page.py"),
    Path("iris/ui/control_actions/hosts.py"),
    Path("iris/system/hermes_memory_nudge.py"),
)

class NamedStash:
    name: str
    paths: tuple[Path, ...]

class MergeResult:
    occupancy_survived: bool
    dedicated_enter_survived: bool
    conflicts: tuple[Path, ...]

def park_unrelated_dirty() -> NamedStash:
    """Stash the silero trio. Do not open or rewrite the files."""
    raise NotImplementedError

def park_merge_overlapping_dirty() -> NamedStash:
    """Stash dirty paths that origin/main also changes. Merge needs a clean index there."""
    raise NotImplementedError

def merge_origin_main() -> MergeResult:
    """git merge origin/main. Do not --strategy=ours on the tree."""
    raise NotImplementedError

def restore_left_occupancy(result: MergeResult) -> None:
    """If occupancy_survived, return. Else put back mount_left_browser and dedicated enter."""
    raise NotImplementedError

def restore_named_stashes(*stashes: NamedStash) -> None:
    raise NotImplementedError
```

`LeftOccupant` is documentation of the domain. Runtime stays the three methods already on `IdeUnifiedShell`. Adding a Python enum to the product is out of scope (laziness-protocol). An agent that treats `mount_workspace` as a substitute for `mount_left_browser` is wrong because the occupant is different.

## Module map (what git moves vs what restore keeps)

| After merge | Owner | This candidate's rule |
| --- | --- | --- |
| `iris/ui/chat/chat_panel.py` and its origin/main imports | origin/main | take theirs. Dedicated remounts the instance. |
| `iris/ui/widgets/drag_tab.py` TTS | origin/main | take theirs. Header chrome of the same window. |
| `iris/runtime/chat_code_exec.py`, `gpt_answer_contract.py` | origin/main | take theirs. ChatPanel closure. |
| wiki/email/obsidian pages, workers, tests | origin/main | land because the merge is whole-tree. Not required for occupancy. |
| `IdeUnifiedShell.mount_left_browser` | serin | keep or restore. |
| `_show_dedicated_browser` / `_exit_dedicated_browser` | serin | keep or restore. |
| `BrowserSession`, `BrowserPanel`, Hermes `browser.*` | serin | keep. origin/main does not own them. |
| silero trio | working tree | park and restore. never merge-edit. |

## Contrast with a file-port

A file-port lists ChatPanel's import graph, copies those files onto `serin`, and leaves `HEAD` unmerged. Occupancy never dies because `ide_companion_page.py` is not replaced by main's class body. wiki/email/obsidian workspace pages stay serin's.

File-port is safer when the goal is dedicated-chat-is-the-same-instance and the ChatPanel closure is already in the working tree. Measured this session, that closure already matches origin/main. The remaining merge payload is the 24-file wiki/email/obsidian rewrite plus the four conflict files. Laziness-protocol picks the file-port in that world, because the class is already there and merge does not make the instance more shared than it is.

Whole-merge is safer when the missing piece is not the ChatPanel file but the send-path hunks inside `main_window.py` that only exist on origin/main (quote strip handling, presenting/stop, exec_python dispatch). Those hunks sit in the same ~9500-line file as dedicated enter. A file-port of `chat_panel.py` leaves `MainWindow` on serin's send-path unless the porter also splices those hunks. That splice is the same conflict as the merge, minus git's 3-way context. Whole-merge is worse when the operator's forbid, the 6583-line side payload, or the dirty silero/wiki index are in force. They are in force today.

## Synthesis decision

Candidate only. Arena fills this after comparing packages.

## Tradeoffs accepted

- We accept landing wiki/email/obsidian (~6583 insertions since merge-base) in exchange for git, not an agent, enumerating ChatPanel's closure and `main_window.py` send-path hunks.
- We accept a four-file conflict round, with hunk-level policy on `main_window.py`, in exchange for not maintaining a hand-synced file list.
- We accept a post-merge occupancy restore in exchange for not forking `IdeUnifiedShell` or adding a second chat widget.
- We accept named stashes of silero and overlapping dirty files in exchange for never opening those silero files.
- We accept that this is a larger diff than the stated dedicated-chat problem, in exchange for ChatPanel and its callers sharing one revision.

## Alternatives considered

- **File-port of ChatPanel plus import closure, no merge.** Smaller public risk. Occupancy survives. Callers still remount `_chat`. It exposes the closure as a hand-synced list (`wiki_quote`, `wiki_study_widgets`, `gpt_answer_contract`, `chat_code_exec`, DragTab TTS, renderer, control_actions/chat). An agent that copies `chat_panel.py` only hits ImportError. An agent that copies the widgets but not `main_window.py` send-path hunks ships a class the window does not drive. Shallower completeness. Wins on laziness and on the user's merge forbid. Loses when the real gap is those window hunks.
- **Merge with `-X ours` on `main_window.py` / `ide_companion_page.py`.** Occupancy survives automatically. ChatPanel class may still come from other files, but window wiring stays serin. Two revisions of one chat feature. Rejected as split ownership of the send-path.
- **Merge and skip restore, then teach dedicated to call `mount_workspace(panel)`.** One left-mount name. It collapses `BrowserPanel` into mail/calendar occupancy (insets, translucent host, `reset_user_ratio`). IDE HWND policy and browser policy share a method. Rejected. Occupants are different facts.

## Open questions and risks

- Should the overlapping dirty ChatPanel/wiki files (already equal to origin/main) be discarded in favor of the merge result, or popped after merge and allowed to conflict with themselves?
- If occupancy restore and main's `resizeEvent` ratio re-apply both write splitter sizes, which one wins on dedicated enter?
- Is landing obsidian/email pages an acceptable side effect if the operator's forbid still stands after this sketch? This candidate does not have a way to merge ChatPanel callers without those pages.
- Do `hosts.py` and `hermes_memory_nudge.py` conflicts hide a control-surface change that dedicated Hermes `browser.*` must keep?

## Next implementation step

Do not merge in this arena. If this candidate is chosen, park the silero trio as a named stash, park merge-overlapping dirty paths, run `git merge origin/main`, and restore occupancy from the four-file conflict policy before popping stashes.
