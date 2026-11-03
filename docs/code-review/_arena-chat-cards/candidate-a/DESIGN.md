# Candidate A — Enrich-in-place (code + shell cards)

Seat: architect arena runner A  
Direction: extend `FencedCodeBlock` / `ToolShellBlock` and HTML helpers in `iris/ui/chat/chat_blocks.py`; pure `parse_fence_info` at the markdown/stream boundary.  
Status: sketch only — bodies described as `raise NotImplementedError` / prose. No production fill-in. No `CardViewModel` layer (Candidate B).

Scope: Cursor-parity for **code + shell cards only**. No Apply, no live approve/sandbox UI.

---

## Problem

Iris already has Cursor-shaped chat cards — `FencedCodeBlock` → language + 「복사」 table, `ToolShellBlock` → collapsible `>_` `<pre>` — but headers stop at language-only and shell has no 「명령 복사」 or clear status chrome. Markdown (`_upgrade_fenced_pre_to_cards`) and streaming (`chat_block_parser` → `CodeSegment.language`) both treat the fence info string as a raw language token, so path/line meta never reaches HTML. Qt Rich Text still forces `<table>` for code padding/borders; shell stays scheme-driven (`iris-copy://`, `iris-collapse://`, `iris-file://`). Constraints from Phase A: keep those public entry points (`fenced_code_to_html` / `tool_shell_to_html` / `render_tool_shell`), enrich the frozen dataclasses in place, put fence parsing in one pure function shared by renderer + stream parser, and ship only the UX gaps above.

---

## Usage (caller's view)

### README (소비자: renderer · streaming · tool insert)

1. Fence info 문자열은 **한 곳**에서만 해석한다: `parse_fence_info(info) -> FenceInfo`.
2. 코드 카드는 항상 `FencedCodeBlock`을 만들어 `fenced_code_to_html(block)`에 넘긴다. path가 있으면 헤더에 경로 + 「열기」(`iris-file://`), 없으면 언어명만 — 호출자는 HTML을 조립하지 않는다.
3. 셸 카드는 기존처럼 `ToolShellBlock` → `tool_shell_to_html` / `marked_tool_shell_to_html` / `render_tool_shell`. command가 있으면 헤더에 「명령 복사」(`iris-copy://` on **command**, not output). status는 정규화 라벨로 표시.
4. Apply · live approve · 새 위젯 스택 · 두 번째 public HTML 빌더 경로는 없다.

### Call site 1 — markdown upgrade (renderer)

```python
# iris/ui/chat/chat_renderer.py — _upgrade_fenced_pre_to_cards
from iris.ui.chat.chat_blocks import (
    FencedCodeBlock,
    fenced_code_to_html,
    parse_fence_info,
)

def _repl(match: re.Match[str]) -> str:
    info = (match.group(1) or "").strip()  # class="language-…" 전체 info
    code = html.unescape(match.group(2) or "")
    meta = parse_fence_info(info)
    if meta.language.lower() == "matrix":
        return matrix_grid_to_html(parse_matrix_grid(code))
    if meta.language.lower() == "diff" or _looks_like_git_diff(code):
        return diff_block_to_html(code)
    block = FencedCodeBlock(
        code,
        language=meta.language,
        path=meta.path,
        start_line=meta.start_line,
        end_line=meta.end_line,
    )
    return fenced_code_to_html(block)
```

### Call site 2 — streaming parser → display

```python
# iris/core/chat_block_parser.py — fence open
from iris.ui.chat.chat_blocks import parse_fence_info

info = raw[fence_end:nl].strip()
meta = parse_fence_info(info)
# CodeSegment keeps a single info source: store language=meta.language for
# highlight, and path/lines for the block (see Shape — CodeSegment fields).
segments.append(
    CodeSegment(
        language=meta.language,
        path=meta.path,
        start_line=meta.start_line,
        end_line=meta.end_line,
        code="",
        complete=False,
    )
)

# iris/ui/chat/chat_display.py — streaming_segments_html
parts.append(
    wrap_document_html(
        fenced_code_to_html(
            FencedCodeBlock(
                seg.code,
                language=seg.language,
                path=seg.path,
                start_line=seg.start_line,
                end_line=seg.end_line,
            )
        )
    )
)
```

### Call site 3 — tool shell insert (unchanged public API)

```python
# iris/ui/chat/chat_panel.py / control_bindings — after RunVisibility
from iris.ui.chat.chat_renderer import render_tool_shell

html = render_tool_shell(
    title="Shell",
    command=card.command,   # clipped ~240 upstream
    output=card.output,     # clipped ~400 upstream
    status=card.status,     # "ok" | "error"
    block_id=bid,
    collapsed=False,
)
# HTML now includes status chip + 「명령 복사」; callers do not build anchors.
```

### Call site 4 — tests (growth target)

```python
# iris/ui/chat/_check_chat_blocks.py
from iris.ui.chat.chat_blocks import parse_fence_info, fenced_code_to_html, FencedCodeBlock

meta = parse_fence_info("python:iris/ui/chat/chat_blocks.py")
assert meta.language == "python" and meta.path == "iris/ui/chat/chat_blocks.py"

html = fenced_code_to_html(
    FencedCodeBlock("x=1", language=meta.language, path=meta.path)
)
assert "iris-file://" in html and "복사" in html and "chat_blocks.py" in html

shell = tool_shell_to_html(
    ToolShellBlock("Shell", "pytest -q", "3 passed", status="ok", block_id="t1")
)
assert "명령 복사" in shell or "iris-copy://" in shell
```

---

## Shape

### Load-bearing decisions

1. **Domain stays the existing frozen cards.** Enrich fields; do not introduce a parallel view-model type.
2. **Fence wire format is owned by `parse_fence_info`.** Renderer and stream parser both call it; neither splits `lang:path` ad hoc (single source of truth / no hand-synced list of patterns outside that function).
3. **Public HTML surface unchanged in name and arity.** Header/actions complexity hides inside `fenced_code_to_html` / `tool_shell_to_html`. Callers pass richer blocks; they do not assemble table cells.
4. **Qt honesty.** Code card remains `<table>` header + body. Shell may keep outer `<pre>` for collapse markers **or** move the chrome row to a one-row `<table>` inside the pre — implementer picks the smallest change that paints status + copy without inventing a widget. Custom schemes only (`iris-file://`, `iris-copy://`, `iris-collapse://`).
5. **Out of scope encoded by absence.** No Apply button, no approve/deny anchors, no unbounded stdout, no Explored-N grouping.

### Interface depth

Public surface stays three HTML entry points + one pure parser + enriched dataclasses. Hidden behind them: fence grammar, display language names, path basename vs full title, open-file enablement policy (reuse existing `file_chip` / IDE-connected helper or always emit `iris-file://` and let click handler no-op), status label mapping, copy-command vs copy-code payload choice. Exposed to callers: block fields they already understand (`code`, `language`, `command`, `status`, …) plus optional `path` / line range. Interface is no larger than needed because a second builder API would create two ways to do one task.

### Types + signatures

```python
# iris/ui/chat/chat_blocks.py  (enrich existing module)

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class FenceInfo:
    """Parsed markdown/stream fence info string. Pure domain; no HTML."""

    language: str = ""
    path: str = ""                 # repo-relative POSIX-ish; "" if unknown
    start_line: Optional[int] = None  # 1-based inclusive; None = unset
    end_line: Optional[int] = None


@dataclass(frozen=True)
class FencedCodeBlock:
    code: str
    language: str = ""
    path: str = ""                 # NEW — header filepath when known
    start_line: Optional[int] = None  # NEW — optional range for title/tooltip
    end_line: Optional[int] = None


@dataclass(frozen=True)
class ToolShellBlock:
    title: str
    command: str
    output: str
    status: str = "ok"             # wire: ok|success|done|error|…
    block_id: str = ""
    collapsed: bool = False
    # No new required fields this slice. Clearer status is derived in HTML
    # from `status` (and optional exit hint already inside `output` from
    # RunVisibility). Copy-command is an HTML action, not stored state.


def parse_fence_info(info: str) -> FenceInfo:
    """Pure boundary parse for fence info / language-class strings.

    Accepted forms (first match wins; unknown → language=stripped info, path=""):
      - "" → empty FenceInfo
      - "python"
      - "python:path/to/file.py"
      - "python path/to/file.py"          # single space separator
      - "path/to/file.py"                 # path-only when looks like a path
      - "12:40:path/to/file.py"           # Cursor start:end:path (language="")
      - "python:12:40:path/to/file.py"    # lang + line range + path

    Invariant: never raises on bad input; never returns HTML.
    highlight_code still receives `.language` only.
    """
    raise NotImplementedError


def fenced_code_from_info(info: str, code: str) -> FencedCodeBlock:
    """Convenience: parse_fence_info + FencedCodeBlock. Optional sugar for
    call sites; not a second HTML path. May be private (`_`) if only tests use it.
    """
    raise NotImplementedError


def fenced_code_to_html(block: FencedCodeBlock) -> str:
    """Code card table. Header left: path basename (title=full path) when
    block.path else display language. Header right: optional 「열기」
    (iris-file:// via file_anchor_for) when path set, then 「복사」
    (iris-copy:// of code). Body: Pygments/highlight_code as today.

    raise NotImplementedError until fill-in; behavior above is the contract.
    """
    raise NotImplementedError


def tool_shell_to_html(block: ToolShellBlock) -> str:
    """Shell tool card. Header: >_ title, status label (성공/실패 or ok/error
    color), 「명령 복사」 when command non-empty (iris-copy:// of command),
    collapse chevron (iris-collapse://). Body: command + output, collapsed
    via existing display toggle. No approve UI.

    raise NotImplementedError until fill-in; behavior above is the contract.
    """
    raise NotImplementedError


def render_tool_shell(
    title: str,
    command: str,
    output: str,
    status: str,
    block_id: str = "",
    *,
    collapsed: bool = False,
) -> str:
    """Unchanged public signature in chat_renderer.py — builds ToolShellBlock
    and wrap_document_html(marked_tool_shell_to_html(...)).
    """
    raise NotImplementedError


# Existing helpers keep ownership of schemes (no duplicate builders):
#   copy_anchor_for / parse_copy_anchor
#   collapse_anchor_for / parse_collapse_block_id
#   file_anchor_for / parse_iris_file_anchor
#   marked_tool_shell_to_html / replace_marked_tool_block / handle_tool_collapse_click
```

```python
# iris/core/chat_block_parser.py — CodeSegment enrichment (same module)

@dataclass
class CodeSegment:
    language: str
    code: str
    complete: bool = False
    path: str = ""                      # NEW — from parse_fence_info
    start_line: Optional[int] = None    # NEW
    end_line: Optional[int] = None      # NEW
```

When emitting `RenderOp` / `FencedCodeBlock`, copy path and lines through — do not re-parse from `language`.

### Validation / invariants

| Invariant | Where encoded |
|---|---|
| Fence string grammar | `parse_fence_info` only |
| One code-card HTML builder | `fenced_code_to_html` |
| One shell-card HTML builder | `tool_shell_to_html` (+ marked wrapper) |
| Copy payload for code vs command | code → copy code; shell header → copy command |
| Collapse state | `ToolShellBlock.collapsed` + existing registry in panel |
| No Apply / approve | no fields, no schemes, no call sites |

### Deliberately does not do

- CardViewModel / presenter layer
- React or QWidget card stack
- Live shell approve, sandbox badges, streaming stdout dump
- Changing RunVisibility clip limits
- Diff/matrix special cases move; they still branch **before** `fenced_code_to_html`

### Data flow

```
markdown language-class / stream fence info
        │
        ▼
  parse_fence_info  ──► FenceInfo
        │
        ▼
  FencedCodeBlock(code, language, path, start_line, end_line)
        │
        ▼
  fenced_code_to_html  ──► <table> card (path|lang · 열기? · 복사)

RunVisibility / insert_tool_shell
        │
        ▼
  ToolShellBlock(...)
        │
        ▼
  tool_shell_to_html → marked_tool_shell_to_html → render_tool_shell
        │
        ▼
  shell card (status · 명령 복사 · collapse)
```

---

## Module map

| Module | Role after change |
|---|---|
| `iris/ui/chat/chat_blocks.py` | **Owner.** `FenceInfo`, enriched blocks, `parse_fence_info`, richer HTML headers. Scheme helpers stay here. |
| `iris/ui/chat/chat_renderer.py` | Call `parse_fence_info` in `_upgrade_fenced_pre_to_cards`; `render_tool_shell` signature unchanged. |
| `iris/core/chat_block_parser.py` | Call `parse_fence_info` on fence open; extend `CodeSegment`; pass fields into `FencedCodeBlock`. |
| `iris/ui/chat/chat_display.py` | Pass `path` / lines into `FencedCodeBlock` when building streaming HTML. |
| `iris/ui/chat/run_visibility.py` | Untouched this slice (still clips command/output into shell fields). |
| `iris/ui/chat/chat_panel.py` | Untouched public insert path; benefits from richer `tool_shell_to_html`. |
| `iris/ui/chat/_check_chat_blocks.py` | Grow asserts: fence parse forms, path header + `iris-file://`, shell command copy. |

No new package. No `card_view_model.py`.

---

## Synthesis decision

(orchestrator fills)

---

## Tradeoffs accepted

- We accept **flat optional fields on `FencedCodeBlock`** (path, lines) instead of a nested `FenceInfo` member in exchange for zero churn at call sites that already construct `FencedCodeBlock(code, language=…)`.
- We accept **keeping shell on `<pre>`-based chrome** (with possible inner table) in exchange for not rewriting collapse/marker HTML and panel click handling in this slice.
- We accept **heuristic fence grammar** (colon/space/path-looking) in one function in exchange for Cursor-like headers without requiring producers to emit a new structured protocol.
- We accept **always showing 「열기」 when path is set** (click may no-op if IDE unbound) in exchange for not threading IDE-connected flags through every code-card call site — or, if implementer reuses `_ide_connected_for_file_chips`, we accept that dependency only inside `fenced_code_to_html` (same depth as file chips). Prefer the latter when easy; do not push the flag onto `FencedCodeBlock`.
- We accept **no new ToolShellBlock fields** this slice in exchange for deriving status chrome from existing `status` / `output`; exit codes already appear in RunVisibility output bits.

---

## Alternatives considered

*(Within Enrich-in-place only — not Candidate B's CardViewModel.)*

1. **Nested `meta: FenceInfo` on `FencedCodeBlock`.** Hides path/lines behind one field and mirrors parse output, but every call site becomes `FencedCodeBlock(code, meta=…)` or dual constructors — deeper type, wider caller churn, same HTML surface. Lost to flat optional fields for interface depth at the construction boundary.
2. **New `iris/ui/chat/fence_meta.py` module** owning only `parse_fence_info` + `FenceInfo`.** Clean temporal split (parse vs render), but splits ownership of one domain (chat card meta) across two importable modules and invites a second call path that forgets the HTML owner. Lost to keeping parse next to the blocks it feeds (`boundary-discipline` + avoid shallow/split modules).
3. **Parse inside `fenced_code_to_html` by stuffing the raw info string into `language`.** Zero parser call-site edits, but re-encodes wire format in the HTML layer, leaves streaming still storing opaque strings, and creates two interpretations of `language` (highlight token vs fence blob). Lost — information leakage and two ways to mean "language".

---

## Open questions and risks

- Should path-only fences (`iris/foo.py` with no language) drive Pygments via extension sniff, or stay unhighlighted plain escape?
- Is `python:12:40:path` required day one, or can line-range forms wait until a producer emits them (Iris markdown today rarely does)?
- For 「열기」, must the header link include `:line` / `:line:col` when `start_line` is set (reuse `parse_file_chip_location` consumers), or is path-only enough for this slice?
- Will putting both 「열기」 and 「복사」 in one header row overflow narrow companion chat width on long basenames — truncate with `title=` full path?
- Does shell 「명령 복사」 label need exact Cursor copy (icon-only) for parity, or is Korean text consistent with existing 「복사」 on code cards?

---

## Next implementation step

Add `FenceInfo` + `parse_fence_info` with table-driven asserts in `_check_chat_blocks`, then thread meta into `FencedCodeBlock` and grow `fenced_code_to_html` header before touching shell chrome.

---

## Red-flag screen (`design-red-flags.md`)

| Flag | Status |
|---|---|
| Shallow module | Pass — same small public HTML API; more behavior inside. |
| Information leakage | Pass if callers only use `parse_fence_info`; fail if renderer/parser keep private splits — sketch forbids that. |
| Temporal decomposition | Pass — parse + HTML stay in `chat_blocks` knowledge boundary; renderer/parser are thin adapters. |
| Pass-through method | `render_tool_shell` remains a thin wrap (document + markers) — acceptable existing policy boundary, not a new empty layer. |
| Split ownership | Pass — one owner for fence grammar and card HTML fields. |
| Two ways to do one task | Pass — single code/shell HTML builders; sugar `fenced_code_from_info` must not become a second HTML API. |
| Importable internals | Pass — private helpers stay `_`-prefixed; no new public chrome builders. |
| Hand-synced list | Pass — fence forms live only in `parse_fence_info`; `_LANG_DISPLAY_NAMES` remains the sole display map. |
