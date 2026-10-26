# Rationale. Port the ChatPanel stack, graft chrome, keep dedicated remount

## Problem

Dedicated browser on this branch already remounts `MainWindow._chat` onto `IdeUnifiedShell` and puts `BrowserPanel` on the left via `mount_left_browser`. origin/main (74c1a19) has the chat the user wants. Wiki quote chips, `_presenting` / stop-during-typing, GPT matrix fences, `chat.exec_python`, header TTS, hover-reveal splitter. Merging main also brings wiki/email/obsidian and **deletes** `mount_left_browser`. Cloning `ChatPanel` onto dedicated would give two composers. Neither is allowed.

The consumer is the person who opens dedicated browser and keeps talking in the same thread they used on home. The maintainer is whoever next touches chat or the shell. They should see one widget and one left-occupant API, not a merge artifact.

## Usage (caller's view)

Call sites are in DESIGN.md. Dedicated enter remounts `self._chat`. TTS chrome talks to `VoicePreferences` through `DragTab`. Presenting is `set_presenting(is_typing_active())`. Quote MIME lands on the composer strip. `chat.exec_python` is a Control Surface action. If a signature disagrees with those sites, change the signature.

## Shape

Data first. One `ChatPanel`. Chat state is that widget plus `_history` / `ChatRunSlot`, not a per-screen copy. `WikiQuote` is a frozen value with `normalized()`. Stop mode is two flags with distinct owners (`generating` vs `presenting`). TTS enabled lives on `VoicePreferences`. Left occupant for dedicated is `_left_browser`, not a second shell. `per model-the-domain`.

Smallest change that gets main's chat without main's product. Checkout the chat files. Extract three quote-strip types so ChatPanel does not import wiki workspace. Graft a handful of MainWindow methods. Copy hover-handle types into this `IdeUnifiedShell`. `per laziness-protocol`.

Do not add `mount_workspace` "for symmetry." Dedicated already has `mount_left_browser`. An extra left-mount with no caller on this branch is a shallow name and a second way to do one task.

Do not checkout `wiki_study_widgets.py`. That module owns preview, FAB, term popover, memos, and chips. Chat only needs chips. Pulling it pulls `wiki_term_explain` and `PageMemoStore`, which is the wiki merge. Composer chips belong next to `ComposerAttachmentStrip`.

Do not checkout `hermes_memory_nudge.py`. Main deletes `browser_teaching_block()`. This branch still drives the page through Hermes. Insert the matrix / `chat.exec_python` paragraphs into HEAD's nudge. Keep browser teaching.

Validation stays at existing boundaries. MIME parse at the composer. `run_chat_python` at the Control Surface. Fence rewrite inside the renderer, display-only. MainWindow trusts `ChatPanel.is_typing_active()`.

## Red-flag screen

**Shallow module.** A wrapper whose public surface is `mount_chat(panel)` around `IdeCompanionPage.mount` hides nothing. `mount_workspace` without mail/wiki callers is the same. Rejected. `mount_left_browser`, `run_chat_python`, and `_CompanionSplitHandle` each hide real policy (insets, whitelist, hover timer).

**Split ownership.** Two `ChatPanel` instances would each write transcript, typing, and presenting. Dedicated already remounts one. Quote chips inside `wiki_study_widgets` would split composer state across chat and wiki. TTS on/off copied onto `ChatPanel` would drift from `VoicePreferences`. `_ide` plus `_left_browser` plus a future `mount_workspace` content pointer would split the left slot three ways. This candidate keeps `_left_browser` for dedicated and leaves Theia as HWND.

**Two ways / pass-through.** `install_companion_shell` on main is a second dedicated-like layout for wiki/email. Not used here. `maybe_attach_plot_markdown` is a helper, not a second exec path. Hermes pastes `chat_markdown`. Do not also auto-merge in MainWindow unless a later caller needs it.

**Information leakage.** ChatPanel does not import `chat_code_exec`. The renderer does not know about tools. Wiki MIME does not leak into `BrowserSession`.

## Synthesis decision

TBD (arena). This is the port-and-graft candidate.

## Tradeoffs accepted

- We accept a two-line ChatPanel import rewrite after checkout, in exchange for not taking wiki workspace modules.
- We accept a new `composer_wiki_quote.py` (~120 lines copied), in exchange for not importing `wiki_study_widgets`. It is not a new abstraction. It is the chip types living in the composer package.
- We accept hand-merging MainWindow TTS/presenting instead of taking the file, in exchange for keeping dedicated `ViewHost` and not importing 6k lines of wiki/email.
- We accept not taking `mount_workspace`, in exchange for one left-occupant API on this branch.
- We accept a surgical nudge insert, in exchange for keeping `browser_teaching_block`.
- We accept dropping `grid_extract` asserts from `_check_gpt_answer_contract.py`, in exchange for not porting morphology/wiki extract.
- We accept `maybe_attach_plot_markdown` unused by MainWindow, in exchange for keeping main's helper next to the fence rewriter. Hermes is the merge caller via paste.

## Alternatives considered

- **`git merge origin/main`.** Gets chat. Also wiki/email/obsidian, deletes `mount_left_browser`, deletes browser nudge teaching. Rejected by constraint and by dedicated regression.
- **Clone `ChatPanel` onto dedicated.** Looks like isolation. It duplicates history and presenting. Remount already exists. Rejected. Split ownership.
- **Checkout `wiki_study_widgets.py` as the listed import dep.** Compiles only with wiki_term_explain and memo store. Wiki merge by import. Rejected.
- **Take `workspace_iris_chat.install_companion_shell` and put dedicated on `mount_workspace`.** Two left-mount APIs. `WorkspaceIrisPanel` even constructs a **second** `ChatPanel`. Rejected for dedicated.
- **Redesign stop mode as a tagged `StopMode` enum while porting.** Cleaner domain, but it rewrites ChatPanel instead of copying main. This candidate copies. A later refactor can collapse the two flags.
- **Skip hover-handle.** Dedicated and IDE share the shell. Main's handle is the chrome the user asked to keep. Leaving the always-visible 6px bar is a visible fork for no benefit.

## Open questions and risks

- After checkout, does `chat_panel.py` from main call any other HEAD-missing symbol besides `wiki_study_widgets`? Measured extra imports are `wiki_quote` and that widget module. Attachment `trace` already exists on HEAD.
- `_check_gpt_answer_contract._assert_nudge_v24_examples` looks for nudge v25 and `chat.exec_python`. If the surgical nudge keeps the v22 marker, that assert must match the marker we keep, or it stays dropped until the insert lands.
- `cyberspace_theme.py` on main also tweaks non-TTS rules (14/5). Taking the whole file risks unrelated chrome. Hand-merge `#WinCtrlTts` only.
- Replay fields (`_tts_replay_*`) must be created in `MainWindow.__init__` (Qt slot abort rule). The graft copies those assignments from main. Do not add them lazily in the speaker slot.
- Quote chips without a wiki workspace mean paste/drop works if some other surface sets the MIME. Dedicated browser will not produce wiki quotes until wiki is ported. The strip can stay empty. That is fine.

## Next implementation step

Do not merge git. Do not touch silero or model_prefs.

1. `git checkout origin/main --` the take-from-main list in DESIGN.md.
2. Add `iris/ui/chat/composer_wiki_quote.py` from the three types in `wiki_study_widgets.py`. Point ChatPanel at it. Do not add `wiki_study_widgets.py`.
3. Graft MainWindow TTS/presenting/replay from 74c1a19. Keep `_show_dedicated_browser`.
4. Merge hover-handle into `ide_companion_page.py`. Keep the left-browser trio. Do not add `mount_workspace`.
5. Insert matrix / `chat.exec_python` into HEAD's hermes nudge. Keep `browser_teaching_block`.
6. Run `_check_chat_stop_button`, `_check_chat_code_exec`, trimmed `_check_gpt_answer_contract`, `_check_browser_workspace`.
