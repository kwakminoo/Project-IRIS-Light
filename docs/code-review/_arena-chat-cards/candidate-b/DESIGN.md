# Candidate B — Chat code/shell cards via view-model boundary

Cursor-parity for **code** and **shell** cards only. No Apply. No live Shell approve / sandbox UI. Qt Rich Text HTML stays.

Forced direction: **view-model boundary.** Wire/parser blocks stay thin. Display fields live on `CodeCardModel` / `ShellCardModel`. HTML takes only view models. One adapter owns mapping.

---

## Problem

Iris already has Cursor-shaped wire types (`FencedCodeBlock`, `ToolShellBlock`) and HTML entry points (`fenced_code_to_html`, `tool_shell_to_html`, `render_tool_shell`, streaming + markdown upgrade paths). Users still miss Cursor parity: filepath header + open-file on code cards, Copy command + clearer status + terminal-like shell card. Qt needs `<table>` for padding/border on code cards; shell is still `<pre>`.

If we enrich the wire dataclasses and grow HTML helpers in the same file, parser/streaming/run_visibility/panel all start knowing display policy (lang labels, status pills, copy payloads, collapse chrome). That scatters Cursor chrome across call sites. This candidate keeps wire thin and puts chrome on view models behind one adapter + one HTML surface.

Constraints from Phase A: keep Qt HTML approach; do not invent a parallel card system; `_check_chat_blocks` must keep passing and grow asserts; out of scope = Apply, live approve, Explored-N.

---

## Usage (caller's view)

Callers keep talking in **wire** or **visibility** terms. They do **not** build header cells, status pills, or `iris-copy://` payloads. Display happens only after `to_code_card` / `to_shell_card` (or the thin facade that does that once).

### README (consumer)

```text
Wire (parser / panel / run_visibility)
  → card_models.to_code_card / to_shell_card
  → card_html.code_card_to_html / shell_card_to_html
  → QTextEdit insertHtml / setHtml
```

Public imports for this slice:

| Who | Imports | Calls |
|---|---|---|
| Streaming / markdown | wire only + existing `fenced_code_to_html` facade | facade maps then renders |
| `insert_tool_block` / control bindings | `ToolShellBlock` or `VisibilityCard` | facade → shell HTML |
| Collapse click | `ShellCardModel` via registry of wire → remap | `shell_card_to_html` |
| New tests | adapter + HTML | assert path/lang/copy/status in HTML |

### Call site 1 — markdown fence upgrade (today’s `_upgrade_fenced_pre_to_cards`)

```python
# after: language class → raw wire; facade hides adapter
from iris.ui.chat.chat_blocks import FencedCodeBlock, fenced_code_to_html

html = fenced_code_to_html(FencedCodeBlock(code, language=lang_or_info_string))
# HTML header shows path when info string had a path; else lang label;
# Copy still iris-copy://; optional iris-file:// when path known
```

### Call site 2 — streaming code segment

```python
# chat_display / RenderOp path — still constructs thin wire
block = FencedCodeBlock(seg.code, language=seg.language)  # language = raw fence info
parts.append(wrap_document_html(fenced_code_to_html(block)))
```

### Call site 3 — tool shell insert (panel / RunVisibility)

```python
# preferred after change: one facade
from iris.ui.chat.chat_blocks import render_tool_shell  # or marked_tool_shell_to_html

bid = panel.insert_tool_block(title="Shell", command=cmd, output=out, status="ok")
# internally: ToolShellBlock → to_shell_card → shell_card_to_html
# card shows status pill, Copy command, collapse chrome, terminal-like body
```

### Call site 4 — tests grow asserts (not a second public path)

```python
from iris.ui.chat.card_models import to_code_card, to_shell_card
from iris.ui.chat.card_html import code_card_to_html, shell_card_to_html

model = to_code_card(FencedCodeBlock(code, language="python:src/app.py"))
html = code_card_to_html(model)
assert "src/app.py" in html and "iris-file://" in html and "iris-copy://" in html

shell = to_shell_card(ToolShellBlock("Shell", "pytest -q", "3 passed", status="ok", block_id="t1"))
assert "복사" in shell_card_to_html(shell) or "Copy" in shell_card_to_html(shell)
assert "ok" in shell_card_to_html(shell).lower() or status pill marker present
```

Usage and Shape agree: **one** way to get code HTML, **one** way to get shell HTML; both require a view model; adapters are the only place fence-meta and status display policy live.

---

## Shape

### Load-bearing decisions

1. **Two layers of data.** Wire = transport/parse identity. View model = everything the card paints.
2. **HTML never reads wire.** `code_card_to_html(CodeCardModel)` / `shell_card_to_html(ShellCardModel)` only. Escaping, tables, anchors happen here.
3. **One adapter module** owns fence-info parsing, lang display names, status pill labels, copy payloads, file anchors, collapse hrefs.
4. **Facades stay** (`fenced_code_to_html(FencedCodeBlock)`, `tool_shell_to_html(ToolShellBlock)`, `render_tool_shell(...)`) as thin `wire → adapter → html` so existing callers do not fork.
5. **Wire stays thin.** Do not add `path`, `lang_label`, `copy_href`, `status_pill` onto `FencedCodeBlock` / `ToolShellBlock`. Parser keeps stuffing raw fence info into `language`; adapter splits it.

### Data structures

```python
# iris/ui/chat/chat_blocks.py  — wire (existing, stay thin)
@dataclass(frozen=True)
class FencedCodeBlock:
    code: str
    language: str = ""  # raw fence info string (may include path); NOT display label

@dataclass(frozen=True)
class ToolShellBlock:
    title: str
    command: str
    output: str
    status: str = "ok"       # ok | error | … raw token
    block_id: str = ""
    collapsed: bool = False


# iris/ui/chat/card_models.py  — view models + adapter (NEW)
@dataclass(frozen=True)
class FenceMeta:
    lang_id: str          # pygments / highlight id (may be "")
    path: str             # "" if unknown
    # line range optional later; not required for this slice
    raw_info: str         # original info string for debugging / fallback


@dataclass(frozen=True)
class CodeCardModel:
    body_code: str              # source text (highlight input)
    lang_id: str                # for highlight_code
    header_primary: str         # path if known else display lang label else ""
    header_secondary: str       # lang label when path is primary; else ""
    copy_payload: str           # plain text for iris-copy://
    file_href: str | None       # iris-file://… or None (disabled chip path handled in HTML)
    open_enabled: bool          # IDE connected? adapter may default True; HTML greys out if False


@dataclass(frozen=True)
class ShellCardModel:
    title: str
    command: str
    output: str
    status_kind: str            # normalized: "ok" | "error" | "running" (running unused this slice)
    status_label: str           # pill text shown to user
    block_id: str
    collapsed: bool
    collapse_href: str          # iris-collapse://…
    copy_command_payload: str   # plain command for iris-copy://
    show_copy_command: bool     # False when command empty


def parse_fence_info(info: str) -> FenceMeta: ...
def to_code_card(block: FencedCodeBlock, *, open_enabled: bool = True) -> CodeCardModel: ...
def to_shell_card(block: ToolShellBlock) -> ShellCardModel: ...
# optional: from VisibilityCard
def shell_card_from_visibility(card: VisibilityCard, *, block_id: str, collapsed: bool = False) -> ShellCardModel: ...


# iris/ui/chat/card_html.py  — HTML only from view models (NEW; or split from chat_blocks)
def code_card_to_html(model: CodeCardModel) -> str: ...
def shell_card_to_html(model: ShellCardModel) -> str: ...


# iris/ui/chat/chat_blocks.py  — facades (keep names; bodies become one-liners)
def fenced_code_to_html(block: FencedCodeBlock) -> str:
    return code_card_to_html(to_code_card(block))

def tool_shell_to_html(block: ToolShellBlock) -> str:
    return shell_card_to_html(to_shell_card(block))
```

### Invariants encoded in types

- Display strings (`header_primary`, `status_label`, hrefs) exist only on view models.
- `FenceMeta` is the single parse result of fence info; HTML does not re-split `language`.
- `status_kind` is a small closed set after adapter normalization; HTML branches on kind, not free-form wire strings.
- Copy anchors are built once in the adapter (payload plain text); HTML only escapes the href.

### Validation ownership

| Concern | Owner |
|---|---|
| Fence info → lang/path | `parse_fence_info` in `card_models` |
| Lang display name map | `card_models` (move `_LANG_DISPLAY_NAMES` here) |
| Clip command/output | `run_visibility` (unchanged); adapter does not re-clip |
| Status token → pill | `to_shell_card` |
| Qt table vs pre layout | `card_html` only |
| Collapse toggle state | wire `ToolShellBlock.collapsed` in panel registry; remap through adapter on each paint |

### Deliberately not done

- Ask-mode Apply / diff apply UI
- Live Shell approve / sandbox
- Unbounded stdout
- Explored-N grouping
- React / WebEngine card rewrite
- Parallel public API that skips the adapter

### Interface depth

Public surface stays the existing facades + wire constructors. Complexity hidden: fence meta grammar, lang labels, file chip enablement, status pill copy, copy-command vs copy-code, table chrome vs shell chrome. Exposed to callers: still `FencedCodeBlock` / `ToolShellBlock` fields they already set. Interface is no larger than today’s entry points; depth comes from moving policy into adapter + HTML.

Principle: `boundary-discipline` — wire vs paint; `one way` — facades funnel all callers.

### Data flow

```text
Markdown / stream fence info string
  → FencedCodeBlock(code, language=raw_info)          # wire thin
  → to_code_card → CodeCardModel
  → code_card_to_html → <table> card

RunVisibility / insert_tool_block / IRIS_TOOL_* body
  → ToolShellBlock(...)                               # wire thin
  → to_shell_card → ShellCardModel
  → shell_card_to_html → terminal-like card HTML

Collapse click
  → replace(block, collapsed=…) in registry
  → tool_shell_to_html(block)  # facade remaps every time
```

---

## Module map

```text
iris/core/chat_block_parser.py
  - still emits FencedCodeBlock / ToolShellBlock (thin)
  - does NOT import card_html or know path/pill chrome

iris/ui/chat/run_visibility.py
  - still emits VisibilityCard → callers build ToolShellBlock
  - optional later: shell_card_from_visibility; not required day one

iris/ui/chat/chat_blocks.py
  - wire dataclasses + anchors + facades
  - HTML bodies for code/shell MOVE OUT (or become re-exports)
  - file_chip / diff / citation / error stay (out of this slice’s ownership change)

iris/ui/chat/card_models.py          [NEW]
  - FenceMeta, CodeCardModel, ShellCardModel
  - parse_fence_info, to_code_card, to_shell_card
  - lang display map, status normalization, copy payloads, hrefs

iris/ui/chat/card_html.py            [NEW]
  - code_card_to_html, shell_card_to_html
  - Qt table/pre policy only; imports models + TOKENS + highlight_code

iris/ui/chat/chat_renderer.py
  - _upgrade_fenced_pre_to_cards still calls fenced_code_to_html facade

iris/ui/chat/chat_display.py / chat_panel.py
  - unchanged call shape; get new HTML via facades

iris/ui/chat/_check_chat_blocks.py
  - keep facade tests; add adapter unit asserts for path/lang/status/copy-command
```

Package rule: outside `iris.ui.chat`, do not import `card_html` or construct view models by hand unless writing tests. Prefer facades.

---

## Synthesis decision

*(Orchestrator / arena synthesis fills this. Candidate B is the view-model-boundary sketch only.)*

---

## Tradeoffs accepted

- We accept an extra module hop (`wire → model → html`) in exchange for keeping parser/panel free of Cursor chrome.
- We accept temporary facade wrappers that look like pass-through in exchange for **one** public way and zero caller churn this slice.
- We accept duplicating a few field names (wire `status` vs model `status_kind`/`status_label`) in exchange for not leaking display policy onto wire.
- We accept shell HTML still using `<pre>` until `card_html` proves a table layout; parity can ship chrome first, layout second, without changing the view-model shape.
- We accept not unifying code+shell into one ADT day one in exchange for two deep, small HTML functions (see rejected alternatives).

---

## Alternatives considered (within this direction)

These are flavors of the view-model boundary, not other arena candidates.

| Alternative | Why it loses |
|---|---|
| **Single `ChatCard` ADT** (`Code \| Shell`) as the only view type | Hides less for callers who already branch on code vs shell; HTML still needs two layouts. Union adds match noise without collapsing policy. Prefer two models + shared adapter module. |
| **Map at every call site** (inline `CodeCardModel(...)` in panel/renderer/parser) | Two ways + information leakage; agents copy the nearest constructor. Violates one adapter. |
| **Promote display fields onto wire dataclasses, then “view model = wire”** | Collapses the boundary; parser starts owning path/pill. That is Candidate A’s shape, rejected here by force. |
| **Parser emits view models directly** | Temporal coupling: stream buffer owns paint policy. Wire markers and collapse registry still need thin identity types → split ownership of the same card. |
| **HTML helpers take wire *or* model (overloads)** | Two ways to do one task; agents pick the wrong one and skip path parsing. Facades only. |

---

## Red-flag screen

| Flag | Status | Notes |
|---|---|---|
| Shallow module | Pass | Facades stay small; depth is fence/status/chrome policy behind `to_*` + `*_to_html`. |
| Information leakage | Pass if enforced | Fence grammar and status pills live only in `card_models`. HTML must not re-parse `language`. |
| Temporal decomposition | Pass | Adapter is knowledge-owned (display mapping), not a load/validate/save pipeline. |
| Pass-through method | Watch | Facades are intentional compatibility shims with adaptation inside; do not add a second shim layer (`render_tool_shell` → `tool_shell_to_html` → `shell_card_to_html` already exists — collapse to one adaptation step). |
| Split ownership | Pass | Collapse state stays on wire in panel registry; paint always remaps. |
| Two ways to do one task | Pass | Delete any direct `code_card_to_html` call sites from product code except facades/tests. |
| Importable internals | Mitigate | Prefer documenting “import facades”; Python cannot hide modules — tests may import `card_models`; product code outside chat should not. |
| Hand-synced list | Pass | `_LANG_DISPLAY_NAMES` moves once into `card_models`; HTML does not keep a second map. |

---

## Open questions and risks

- Should fence info grammar follow Cursor’s `lang:path` / `path` / `lang` exactly, or a smaller Iris subset for this slice?
- When both path and language are present, is header primary always path (Cursor) with lang as muted secondary?
- Does `open_enabled` need a real IDE-connected probe at map time, or reuse existing file-chip greying inside HTML the way `file_chip_to_html` does today?
- Shell card: keep `<pre>` for collapse body, or move shell to `<table>` in the same change as Copy-command/status pill?
- Should `VisibilityCard` gain a direct `shell_card_from_visibility`, or always go `VisibilityCard → ToolShellBlock → to_shell_card` to keep one wire type?

---

## Next implementation step

Add `card_models.py` with `FenceMeta` / `parse_fence_info` / `to_code_card` / `to_shell_card` and failing `_check_chat_blocks` asserts for path header + shell copy-command, then point `fenced_code_to_html` / `tool_shell_to_html` through them without changing call sites.
