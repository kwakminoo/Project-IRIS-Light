# DESIGN. Port ChatPanel from origin/main, do not merge main (candidate 1)

Organizing structure. One `ChatPanel` owned by `MainWindow`. Dedicated browser already remounts that instance onto `IdeUnifiedShell`. Port the origin/main (74c1a19) chat stack by checkout, not by merging `origin/main`. Graft TTS/presenting onto this branch's `MainWindow`. Merge the hover-reveal splitter handle into this branch's `IdeUnifiedShell` while keeping `mount_left_browser` / `left_browser` / `clear_left_browser`.

Failed premise this shape attacks. "To get main's chat (wiki chips, presenting, GPT matrix, `chat.exec_python`, header TTS) we must merge main, or we must clone `ChatPanel` onto the dedicated screen." Both are wrong. The dedicated screen already hosts `self._chat`. Main's chat files are a bounded stack. Wiki/email/obsidian on main are not in that stack.

---

## Usage (caller's view)

### Dedicated browser (already true on this branch)

```python
# iris/ui/window/main_window.py
panel = window._show_dedicated_browser()
# _ui_mode == "dedicated_browser"
# _mount_unified_companion_body() addWidget-moves self._chat onto _companion_page
# _unified_shell.mount(None, self._companion_page, total_w=...)
# _unified_shell.mount_left_browser(panel)
# isinstance(window._chat, ChatPanel) and window._chat is the only composer
# _unified_shell.left_browser() is panel
```

No new chat widget. No `WorkspaceIrisPanel` on this path. IDE-internal browser stays on `IrisIdeWindow._stack`.

### Header TTS and presenting (ported from main, wired here)

```python
# after ChatPanel + DragTab checkout, MainWindow graft only
window._drag.tts_clicked.connect(window._on_tts_header_clicked)
window._drag.set_tts_enabled(bool(window._voice_prefs.tts_enabled))
window._chat.typing_finished.connect(window._sync_chat_stop_for_presentation)

# VoicePreferences.tts_enabled is the source of truth.
# DragTab mirrors it. ChatPanel does not store tts_enabled.

window._sync_chat_stop_for_presentation()
# window._chat.set_presenting(window._chat.is_typing_active())
# TTS playback alone does not hold the stop button.
```

Speaker replay on main restarts the answer instead of stacking jobs. Same graft. Same `self._chat`. If a workspace panel ever passes `chat=`, it is that panel's widget. Dedicated does not pass a second one.

### Composer wiki chips (ported, chat-owned)

```python
# paste / drop of application/x-iris-wiki-quote
panel._on_wiki_quote_pasted(quote)
# ComposerWikiQuoteStrip.add_quote
# send -> format_quotes_for_model(quotes, text)
```

Wiki workspace pages are not required for the chip to exist. The MIME type is the boundary.

### GPT matrix + chat.exec_python (ported)

```python
# display path (ChatPanel / renderer)
html = render_iris_message(text)
# _markdown_body_to_html calls normalize_binary_fences_for_display
# unlabeled 0/1 fences become ```matrix. python fences stay.

# tool path (Control Surface)
result = iris_invoke(action="chat.exec_python", args={"code": "..."})
# run_chat_python whitelist. png_paths + chat_markdown returned.
# Hermes pastes chat_markdown into the reply (nudge). maybe_attach_plot_markdown
# is the merge helper if a caller wants it. MainWindow does not auto-merge.
```

### Splitter handle (merged into this shell)

```python
shell = window._unified_shell
# handle is transparent until 1s hover or drag
# resizeEvent reapplies COMPANION_CONTENT_RATIO or the remembered user ratio
# dedicated still calls mount_left_browser, never mount_workspace
```

---

## Shape

### One chat widget

```text
ChatOwner     = MainWindow
ChatWidget    = MainWindow._chat          # the only ChatPanel for home / IDE / dedicated
ChatState     = widget + _history + ChatRunSlot
ChatMount     = addWidget remount onto assistant column or IdeCompanionPage
```

`ViewHost` already tags dedicated vs `ide_internal`. Chat does not grow a per-screen copy. Mail/calendar `WorkspaceIrisPanel` still constructs its own `ChatPanel` (pre-existing, out of scope). Dedicated must not start using that class.

### Stop button

Two flags on `ChatPanel`, one writer for each.

```text
generating  <- MainWindow.set_generating during the LLM turn
presenting  <- MainWindow.set_presenting(is_typing_active()) after typing_finished
               and after turn boundaries. TTS busy is not presenting.
stop mode   = generating OR presenting
```

Do not add a third boolean for TTS. `is_typing_active()` already includes TTS-synced typing. `_tts_output_busy()` is playback, owned by `MainWindow`, used to cancel/replay, not to hold stop.

### TTS chrome

```text
VoicePreferences.tts_enabled   # owner, persisted
DragTab.set_tts_enabled        # view
MainWindow._on_tts_header_clicked  # toggles owner, mirrors view, starts/stops runtime
```

Replay fields live on `MainWindow` (`_tts_replay_pending`, `_tts_replay_depth`, `_tts_replay_again`, `_tts_replay_token`, `_tts_replay_chat`). They serialize restart. They are not chat-widget state.

### Wiki quote

`WikiQuote` is the typed chip. Composer owns the list. Wiki preview widgets do not.

```text
WikiQuote (frozen) -> MIME bytes <-> ComposerWikiQuoteStrip -> format_quotes_for_model
```

Illegal without a note path or quote text (`normalized()` returns `None`). ChatPanel never imports wiki term-explain or page memos.

### Left occupant of IdeUnifiedShell

This candidate does not add mail/wiki `mount_workspace`. Dedicated and IDE already share the shell.

```text
LeftSlot = empty | theia_hwnd | browser_panel
```

`_left_browser` holds `browser_panel` only. Theia is HWND, so `_ide` stays `None` on both companion and dedicated. Invariant. dedicated enter sets `_left_browser`. dedicated exit calls `clear_left_browser`. Companion never reads `_left_browser` as Theia.

Hover handle, `COMPANION_CONTENT_RATIO`, and `resizeEvent` re-apply are chrome of this same shell. They do not change the occupant type.

### GPT display contract

`normalize_binary_fences_for_display` is display-only. DB / history keep the original fence. `maybe_attach_plot_markdown` is a pure merge of tool payload onto assistant text. It does not run Python.

---

## Signatures

```python
# iris/ui/chat/chat_panel.py  (checkout origin/main, then two import lines)

class ChatPanel(QWidget):
    typing_finished = pyqtSignal()   # finish_typing emitted this
    # existing send_clicked, stop_clicked, speaker_clicked, ...

    def is_typing_active(self) -> bool: ...
    def set_presenting(self, active: bool) -> None: ...
    def is_presenting(self) -> bool: ...
    def set_generating(self, active: bool) -> None: ...
    def is_generating(self) -> bool: ...
    def on_speech_typing_finished(self, *, flush: bool = True) -> None: ...
    def finish_typing(self) -> None: ...
    def _on_wiki_quote_pasted(self, quote: object) -> None: ...
```

```python
# iris/ui/widgets/drag_tab.py  (checkout origin/main; diff vs HEAD is additive TTS)

class DragTab(QWidget):
    tts_clicked = pyqtSignal()
    def set_tts_enabled(self, enabled: bool) -> None: ...
    def set_ide_companion_active(self, active: bool) -> None: ...  # already on HEAD
```

```python
# iris/knowledge/wiki_quote.py  (checkout origin/main; no wiki workspace imports)

WIKI_QUOTE_MIME = "application/x-iris-wiki-quote"

@dataclass(frozen=True)
class WikiQuote:
    note_rel: str
    title: str
    quote: str
    source: str = "wiki"
    def normalized(self) -> WikiQuote | None: ...

def format_quotes_for_model(quotes: list[WikiQuote], user_text: str) -> str: ...
def encode_wiki_quote_bytes(quote: WikiQuote) -> bytes: ...
def decode_wiki_quote_bytes(raw: bytes | str | None) -> WikiQuote | None: ...
def chip_preview(quote: WikiQuote, *, max_chars: int = 120) -> str: ...
```

```python
# iris/ui/chat/composer_wiki_quote.py  (NEW. extracted from main wiki_study_widgets.py)

class WikiQuoteChip(QFrame):
    removed = pyqtSignal()

class ComposerWikiQuoteStrip(QWidget):
    changed = pyqtSignal()
    def quotes(self) -> list[WikiQuote]: ...
    def add_quote(self, quote: WikiQuote) -> None: ...
    def take_quotes(self) -> list[WikiQuote]: ...
    def clear(self) -> None: ...

def parse_wiki_quote_from_mime(source) -> WikiQuote | None: ...
```

```python
# iris/ui/chat/gpt_answer_contract.py  (checkout origin/main)

def normalize_binary_fences_for_display(md: str) -> str: ...
def maybe_attach_plot_markdown(
    assistant_text: str,
    tool_payload: dict[str, Any] | None,
) -> str: ...
```

```python
# iris/runtime/chat_code_exec.py  (checkout origin/main)

def run_chat_python(code: str, *, timeout_s: float = 20) -> dict[str, Any]:
    # ok, stdout, stderr, png_paths, chat_markdown, error
    ...
```

```python
# iris/ui/control_actions/chat.py  (checkout origin/main; +39 lines vs HEAD)

def chat_exec_python(args: dict[str, Any]) -> dict[str, Any]: ...
# register action name "chat.exec_python"
```

```python
# iris/ui/workspaces/ide_companion_page.py  (HAND-MERGE, keep this branch's left-browser API)

COMPANION_CONTENT_RATIO = 0.8
_HANDLE_REVEAL_MS = 1000

class _CompanionSplitHandle(QSplitterHandle):
    def bar_visible(self) -> bool: ...   # optional; main has it

class _CompanionSplit(QSplitter):
    def createHandle(self) -> QSplitterHandle: ...

class IdeUnifiedShell(QWidget):
    _left_browser: QWidget | None
    def mount_left_browser(self, panel: QWidget) -> None: ...
    def left_browser(self) -> QWidget | None: ...
    def clear_left_browser(self) -> None: ...
    def mount(self, ide: QWidget | None, companion: IdeCompanionPage, *, total_w: int) -> None: ...
    def apply_ratio(self, total_w: int, ratio: float | None = None) -> None: ...
    def resizeEvent(self, event) -> None: ...
    # do not add mount_workspace on this candidate
    # do not delete the left-browser trio
```

```python
# iris/ui/window/main_window.py  (HAND-MERGE graft only; never checkout this file)

class MainWindow:
    # __init__ fields from main 74c1a19
    _tts_replay_pending: bool
    _tts_replay_depth: int
    _tts_replay_again: bool
    _tts_replay_token: str
    _tts_replay_chat: ChatPanel | None

    def _on_tts_header_clicked(self) -> None: ...
    def _tts_output_busy(self) -> bool: ...
    def _sync_chat_stop_for_presentation(self) -> None: ...
    def _on_chat_speaker_clicked(self, token: str, chat=None) -> None: ...
    def _fire_tts_replay(self) -> None: ...
    def _start_tts_replay(self, token: str, chat) -> None: ...
    # _show_dedicated_browser / _mount_unified_companion_body stay as on this branch
```

Dedicated remount stays this (already on the branch).

```text
_show_dedicated_browser
  _mount_unified_companion_body     # addWidget self._chat onto _companion_page
  _unified_shell.mount(None, companion)
  _unified_shell.mount_left_browser(panel)
```

---

## Module map

```text
MainWindow._chat  -------------------------------\
  ChatPanel (origin/main file)                    \
    composer_wiki_quote  (extracted, chat-owned)   }  one widget, remounted
    wiki_quote           (origin/main file)        /
    chat_renderer -> gpt_answer_contract          /
    composer_attachments, composer_plus_menu      /
DragTab (origin/main file)  <- TTS chrome view
VoicePreferences            <- TTS owner (do not touch silero / model_prefs files)
chat_code_exec              <- chat.exec_python body
control_actions/chat.py     <- registration
IdeUnifiedShell             <- this branch + hover handle from main
  mount_left_browser        <- dedicated left occupant (keep)
  _CompanionSplitHandle     <- from main
BrowserPanel / BrowserSession / Hermes tools  <- untouched
```

### Take from origin/main (checkout / copy verbatim)

Measured at HEAD 7ec6656 vs origin/main 74c1a19.

| File | Why it is the chat stack |
| --- | --- |
| `iris/ui/chat/chat_panel.py` | presenting, wiki strip, typing_finished. After copy, rewrite the `wiki_study_widgets` import to `iris.ui.chat.composer_wiki_quote`. Two lines. |
| `iris/ui/chat/chat_renderer.py` | calls `normalize_binary_fences_for_display` |
| `iris/ui/chat/gpt_answer_contract.py` | new on main |
| `iris/ui/chat/_check_chat_blocks.py` | main's chat-block check |
| `iris/ui/widgets/drag_tab.py` | +71 TTS only vs HEAD. Additive. |
| `iris/knowledge/wiki_quote.py` | typed quote. No wiki page imports. |
| `iris/runtime/chat_code_exec.py` | new on main |
| `iris/runtime/_check_chat_code_exec.py` | new on main |
| `iris/ui/control_actions/chat.py` | +39 `chat.exec_python` vs HEAD. Additive. |
| `iris/ui/_check_chat_stop_button.py` | presenting + typing_finished asserts |

Same as HEAD already (do not overwrite). `chat_display.py`, `chat_blocks.py`, `composer_attachments.py`, `composer_plus_menu.py`.

### Hand-merge (do not checkout the whole file)

| File | Take from main | Keep from this branch |
| --- | --- | --- |
| `iris/ui/workspaces/ide_companion_page.py` | `_CompanionSplitHandle`, `_CompanionSplit`, transparent handle stylesheet, `COMPANION_CONTENT_RATIO`, `resizeEvent` ratio re-apply | `mount_left_browser`, `left_browser`, `clear_left_browser`, `_left_browser`, dedicated-safe `mount` |
| `iris/ui/window/main_window.py` | TTS header connect, `_on_tts_header_clicked`, `_tts_output_busy`, `_sync_chat_stop_for_presentation`, replay fields + `_fire_tts_replay` / `_start_tts_replay`, `_cancel_current_turn` presenting branch, `set_tts_enabled` after prefs save | dedicated/ide_internal `ViewHost`, `_show_dedicated_browser`, `_mount_unified_companion_body`, BrowserSession wiring. No wiki/email/obsidian blocks. |
| `iris/ui/shared/cyberspace_theme.py` | `#WinCtrlTts` rules next to `#WinCtrlMic` | everything else |
| `iris/system/hermes_memory_nudge.py` | items 21-22 (matrix fences + `chat.exec_python`) and the WRONG/CORRECT contract | v22 marker/body, `browser_teaching_block()`, browser.search presence checks. Main's file **deletes** browser teaching. |
| `iris/ui/chat/_check_gpt_answer_contract.py` | `_assert_normalize_binary_fences`, `_assert_maybe_attach_plot` | drop `_assert_extract_confidence` (needs `grid_extract`, not on HEAD). Keep nudge assert only after the surgical nudge graft. |

### Extract (new file, copied symbols, not the wiki module)

From `origin/main:iris/ui/knowledge/wiki_study_widgets.py`, only `WikiQuoteChip`, `ComposerWikiQuoteStrip`, `parse_wiki_quote_from_mime`. Write them as `iris/ui/chat/composer_wiki_quote.py`. Imports `iris.knowledge.wiki_quote` only.

### Do not take from origin/main

- Whole `origin/main` merge (wiki/email/obsidian, ~6k lines).
- `iris/ui/knowledge/wiki_study_widgets.py` and its imports `wiki_term_explain`, `wiki_page_memos`.
- `iris/knowledge/grid_extract.py`, `wiki_import_ops.py`, `wiki_original.py`, `wiki_save_intent.py`.
- `iris/ui/workspaces/workspace_iris_chat.py` (`install_companion_shell` / `mount_workspace` / wiki shell). Pulls a second layout path and does not serve dedicated.
- `IdeUnifiedShell.mount_workspace` / `splitter()` unless a caller on this branch needs them. Dedicated does not.
- Whole `main_window.py` or whole `ide_companion_page.py`.
- `iris/runtime/attachment_context.py` (exists on both, hashes differ, not this stack).
- silero / `model_prefs` / voice-runtime model files.

---

## Rejected shapes

**Full merge of origin/main.** Gets chat, and also wiki/email/obsidian. User forbade it. Main's `IdeUnifiedShell` **deletes** `mount_left_browser`. Main's nudge **deletes** `browser_teaching_block`. That is a dedicated-browser regression.

**Clone ChatPanel for dedicated.** Two composers, two histories, two presenting flags. Dedicated already remounts `self._chat`. A second widget is split ownership of chat state.

**Checkout `wiki_study_widgets.py` as the ChatPanel import dep.** The file is wiki preview + FAB + term popover + memos + chips. Importing it requires `wiki_term_explain` and `PageMemoStore`. That is the wiki merge by the back door.

**Add `mount_workspace` "for later" and route dedicated through it.** Two ways to put a Qt widget on the left. Dedicated already has `mount_left_browser`. Extra method with no caller on this branch.

**New `DedicatedChatHost` wrapper.** Pass-through around `IdeCompanionPage.mount(chat=self._chat)`.

---

## Red-flag screen

**Shallow module.** `mount_left_browser` hides addWidget + inset-zero + show. Callers do not set layout margins. Hover handle hides timer/paint. `run_chat_python` hides whitelist/Agg/timeout. `normalize_binary_fences_for_display` hides fence policy. Rejected extras (`DedicatedChatHost`, unused `mount_workspace`) would expose more names and hide nothing.

**Split ownership.** One `ChatPanel` writer for transcript and presenting flags. One `VoicePreferences` writer for TTS on/off. One `_left_browser` writer for the dedicated occupant. Quote chips live in the composer module, not the wiki workspace module. MainWindow writes `set_presenting` from `is_typing_active()`; it does not keep a parallel typing flag.

**Two ways.** One remount path (`_mount_unified_companion_body`). One left-browser API. One `chat.exec_python` registration. Do not also open dedicated via `install_companion_shell`.

**Pass-through / information leakage.** ChatPanel talks quote MIME only through `parse_wiki_quote_from_mime`. Renderer does not import `chat_code_exec`. Control action does not import `ChatPanel`.

---

## Checks (later implementation, not this write)

```text
python -m iris.ui._check_chat_stop_button
python -m iris.runtime._check_chat_code_exec
python -m iris.ui.chat._check_gpt_answer_contract   # trimmed file
python -m iris.ui.workspaces._check_browser_workspace
# asserts left_browser is panel, self._chat in companion mount, set_presenting, set_tts_enabled
```

Do not run a git merge. Do not edit silero or model_prefs.
