# Candidate B — Control-action / worker path

Seat: architect arena runner B  
Feature: chip PDF → dump every lab script to files (bypass 24k model stuffing)  
Direction: new `content.dump_lab_scripts` + `LabDumpWorker` QThread; Hermes or thin preflight calls it; parse+write outside MainWindow; nudge/system forces the tool on matching intent.

---

## Problem

Chip PDF attachments go through `AttachmentWorker` → `prepare_attachments` with `MAX_CONTEXT_CHARS` 24k. Large lecture PDFs arrive as `truncated=true` + partial `BEGIN ATTACHMENT TEXT`. Hermes then either asks the user to paste or calls `content.extract`, which returns a long `text` payload into the model context — still stuffing the 24k budget and failing late labs (e.g. `7-7`). The needed outcome is disk files named as in the PDF, not a model that re-emits every program body. Global caps (`MAX_FILE_BYTES`, `MAX_CONTEXT_CHARS`, `MAX_PDF_PAGES`, `VISION_PAGE_CAP`, `content_extract._MAX_CHARS`) stay locked. Parse and write must not grow another MainWindow boolean; they live in a pure module, invoked by a control action and/or a QThread worker, with Hermes seeing only a short written-path summary.

## Usage (caller's view)

### Consumer README

When a user attaches a lecture PDF and asks to create every practice program (`실습 전부 만들어`, `프로그램 7-5부터 전부 파일로`), Iris does **not** paste the PDF into Hermes. A caller (Hermes via `iris_invoke`, or a thin preflight) calls `content.dump_lab_scripts` with the Attachment absolute path. The action reads the PDF page-by-page (same hybrid stack as `read_pdf_pages`), parses program labels, writes files under the open project (default folder `labs/`), and returns only labels + paths. Chat gets a short fixed or model reply listing what was written.

### Call site 1 — Hermes tool (primary)

```python
# Hermes / Iris Agent turn (conceptual iris_invoke)
result = iris_invoke(
    action="content.dump_lab_scripts",
    args={
        "source": r"C:\Users\...\AppData\Local\...\chip-lecture.pdf",  # Attachment path
        # project_root optional: defaults to bound IDE / Iris project root
        # out_dir optional: default "labs"
        # overwrite optional: default False (skip existing same bytes / keep file)
    },
)
# result.ok, result.data == {
#   "written": ["labs/7-5.py", "labs/7-6.py", "labs/7-7.py"],
#   "labels": ["7-5", "7-6", "프로그램 7-7"],
#   "count": 3,
#   "truncated_pages": False,
#   "errors": [],
# }
# NO program bodies in result.data — model never receives full PDF text from this tool.
```

### Call site 2 — Thin preflight (MainWindow turn gate)

```python
# iris/ui/window/main_window.py — after chip paths known, before Hermes stuffing
from iris.knowledge.lab_dump_intent import is_lab_dump_intent, pick_pdf_source
from iris.ui.workers.lab_dump_worker import LabDumpWorker

if is_lab_dump_intent(turn.text, attachment_paths) and (pdf := pick_pdf_source(attachment_paths)):
    worker = LabDumpWorker(
        source=pdf,
        project_root=self._project_root(),
        out_dir="labs",
        parent=self,
    )
    worker.finished_ok.connect(self._on_lab_dump_done)   # present short reply; skip Hermes or continue with summary only
    worker.failed.connect(self._on_lab_dump_failed)
    worker.start()
    return  # do not run prepare_attachments → 24k BEGIN ATTACHMENT TEXT for this turn
```

### Call site 3 — Pure module (tests / worker body)

```python
from pathlib import Path
from iris.knowledge.lab_script_dump import dump_lab_scripts_from_pdf

summary = dump_lab_scripts_from_pdf(
    Path(pdf),
    project_root=Path(root),
    out_dir="labs",
    overwrite=False,
    page_limit=200,  # MAX_PDF_PAGES
    cancelled=lambda: False,
)
assert summary.written  # relative paths under project_root
# summary never includes bodies in the Hermes-facing dict; LabDumpResult.programs stays in-process only
```

---

## Shape

### Data structures (first)

```python
# iris/knowledge/lab_script_dump.py

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class LabProgram:
    """One labeled practice block from a lecture PDF."""

    label: str          # as printed, e.g. "7-5" or "프로그램 7-7"
    filename: str       # safe relative name, e.g. "7-5.py"
    body: str           # source text only — never copied into Hermes messages
    pages: tuple[int, ...]


@dataclass(frozen=True)
class LabDumpResult:
    """In-process dump outcome. programs may be large; strip before any model boundary."""

    programs: tuple[LabProgram, ...]
    written: tuple[str, ...]          # rel_path under project_root
    errors: tuple[str, ...]
    truncated_pages: bool             # True if page_limit hit before EOF


@dataclass(frozen=True)
class LabDumpSummary:
    """Wire / Hermes-facing payload. Invariant: no bodies, no page text."""

    written: tuple[str, ...]
    labels: tuple[str, ...]
    count: int
    truncated_pages: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict:
        raise NotImplementedError


def label_to_filename(label: str, *, default_ext: str = ".py") -> str:
    """Map PDF label → safe single-segment filename. Invariant: no path separators."""
    raise NotImplementedError


def parse_lab_programs(page_texts: list[tuple[int, str]]) -> list[LabProgram]:
    """Pure parse over (1-based page, text) pairs. No I/O. Dominant access: sequential page scan + label regex."""
    raise NotImplementedError


def dump_lab_scripts_from_pdf(
    source: Path,
    *,
    project_root: Path,
    out_dir: str = "labs",
    overwrite: bool = False,
    page_limit: int | None = None,
    vision_reader=None,
    cancelled: Callable[[], bool] | None = None,
) -> LabDumpResult:
    """Extract pages via read_pdf_pages hybrid, parse, write via write_project_file.

    Invariants:
    - Does not append page text into chat / Hermes message buffers.
    - Honors MAX_PDF_PAGES (default page_limit), MAX_FILE_BYTES on source size check.
    - Idempotent: overwrite=False skips existing path with matching UTF-8 content;
      partial crash → rerun writes remaining / refreshes mismatched.
    """
    raise NotImplementedError


def to_hermes_summary(result: LabDumpResult) -> LabDumpSummary:
    """Boundary strip: drop bodies before any tool result reaches the model."""
    raise NotImplementedError
```

```python
# iris/knowledge/lab_dump_intent.py

from __future__ import annotations

from pathlib import Path


def is_lab_dump_intent(text: str, attachments: list[str] | tuple[str, ...] = ()) -> bool:
    """True when user wants every practice/lab program written from an attached PDF.

    Keywords (KO/EN): 실습, 프로그램 N-M, 전부/모두 만들어|파일로|작성, lab script, dump labs.
    Requires a PDF among attachments or an explicit .pdf path in text.
    Does not match wiki-save or note.export_pdf intents (those win first).
    """
    raise NotImplementedError


def pick_pdf_source(attachments: list[str] | tuple[str, ...], text: str = "") -> str | None:
    """First usable absolute PDF path from chips or quoted path in text."""
    raise NotImplementedError
```

```python
# iris/ui/workers/lab_dump_worker.py

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class LabDumpWorker(QThread):
    """PDF parse+write off the Qt GUI thread (same role as AttachmentWorker)."""

    finished_ok = pyqtSignal(object)  # LabDumpSummary.to_dict()
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)        # optional short status for chat chrome

    def __init__(
        self,
        source: str,
        *,
        project_root: str = "",
        out_dir: str = "labs",
        overwrite: bool = False,
        vision_reader=None,
        parent=None,
    ) -> None:
        raise NotImplementedError

    def request_cancel(self) -> None:
        raise NotImplementedError

    def run(self) -> None:
        # TODO: bind vision reader if needed; call dump_lab_scripts_from_pdf;
        # emit to_hermes_summary(...).to_dict(); never emit program bodies.
        raise NotImplementedError
```

```python
# iris/ui/control_actions — content_dump_lab_scripts (register next to content.extract)

def content_dump_lab_scripts(args: dict) -> dict:
    """Control action: content.dump_lab_scripts.

    Args: source|path (required), project_root?, out_dir?=labs, overwrite?=false.
    If invoked on the Qt GUI thread, spawn LabDumpWorker and wait via existing
    off-UI / pump helper pattern used by long project actions — or run pure dump
    when already off-UI (Hermes MCP invoke thread).
    Returns ok_result with LabDumpSummary.to_dict() only.
    """
    raise NotImplementedError
```

### Flow

```
chip PDF + "실습 전부 파일로"
        │
        ├─[preflight] is_lab_dump_intent? ──yes──► LabDumpWorker
        │                                              │
        │                                              ▼
        │                                    dump_lab_scripts_from_pdf
        │                                      (read_pdf_pages / OCR)
        │                                      parse_lab_programs
        │                                      write_project_file × N
        │                                              │
        │                                              ▼
        │                                    LabDumpSummary → chat reply
        │                                    (skip 24k attachment stuffing)
        │
        └─[Hermes path] attachment metadata/path only (no full body)
                 + nudge 15h forces content.dump_lab_scripts
                 → same pure dump → short tool result → model lists paths
```

### Load-bearing decisions

1. **Public surface is one action** — `content.dump_lab_scripts`. Callers never see page text or `LabProgram.body` (interface depth: hide extract/parse/write behind one invoke).
2. **Types encode the model boundary** — `LabDumpResult` (in-process, has bodies) vs `LabDumpSummary` (wire, no bodies). `to_hermes_summary` is the only legal crossing (boundary-discipline).
3. **Reuse extract stack, not chat budget** — page walk uses `read_pdf_pages` with `MAX_PDF_PAGES`; dump accumulation is disk-bound, not `MAX_CONTEXT_CHARS`. Chat attachment prepare is skipped or path-only on this intent.
4. **Worker owns long work** — OCR/hybrid PDF must not block MainWindow slots (Qt slot abort / freeze risk). Control action uses the worker when on the GUI thread.
5. **Nudge forces the tool** — `hermes_memory_nudge` rule: on lab-dump intent + PDF Attachment path, call `content.dump_lab_scripts`; do not call `content.extract` for full refill; do not loop `project.write_file` with pasted bodies.
6. **MainWindow stays thin** — intent check + start worker + present summary. No parse regex, no PDF loops in `main_window.py`.

### Deliberately does not

- Raise `MAX_CONTEXT_CHARS` or special-case attachment stuffing for lecture PDFs.
- Return `text` like `content.extract` (that path remains for Q&A excerpts).
- Ask the model to shell PyMuPDF / write scripts from memory of truncated chips.
- Add an IDE PDF viewer.

### Module map

| Module | Role |
|--------|------|
| `iris/knowledge/lab_script_dump.py` | Types, parse, dump, Hermes strip (pure + I/O write) |
| `iris/knowledge/lab_dump_intent.py` | Intent / PDF path pick (mirror `wiki_save_intent`) |
| `iris/ui/workers/lab_dump_worker.py` | `LabDumpWorker` QThread |
| `iris/ui/control_actions/wiki.py` (or split `content.py`) | Register `content.dump_lab_scripts` |
| `iris/ui/control_actions/action_catalog.json` | Catalog entry + Hermes-facing summary |
| `iris/system/hermes_memory_nudge.py` | Rule 15h: force dump tool, forbid extract-stuff |
| `iris/ui/window/main_window.py` | Thin preflight only |
| `iris/runtime/attachment_context.py` | Untouched limits; optional path-only prepare helper if preflight needs metadata without body |
| `iris/knowledge/content_extract.py` | Reuse `read_pdf_pages` only |
| `iris/system/project_ops.py` | Reuse `write_project_file` |
| `iris/ui/_check_lab_script_dump.py` | Self-check: parse labels, no body in summary dict, intent gate |

### Catalog sketch

```json
{
  "name": "content.dump_lab_scripts",
  "summary": "From a lecture PDF path, parse every practice/lab program label and write source files under the project (default labs/). Returns written paths and labels only — not PDF text. Prefer this over content.extract + project.write_file when the user wants all labs as files. Pass Attachment absolute path.",
  "risk": "medium",
  "confirm_required": false
}
```

---

## Synthesis decision

*(Arena synthesis fills this. Runner B candidate only.)*

Base not yet chosen. This package is the **control-action + worker** whole-shape alternative: tool-first with optional preflight, vs enrichment-inside-attachment or model-orchestrated extract/write loops.

---

## Tradeoffs accepted

- We accept a **second content.* action** (alongside `content.extract`) in exchange for a hard guarantee that dump results never carry PDF bodies into the model.
- We accept **preflight short-circuit** (sometimes skip Hermes) in exchange for not depending on the model remembering to call the tool when 15h nudge fails.
- We accept **default `labs/` subfolder** in exchange for not scattering many `7-*.py` on the project root; callers can override `out_dir`.
- We accept **OCR/vision cost on the worker** (up to `MAX_PDF_PAGES`) in exchange for complete late-page labs without raising chat 24k.
- We accept **partial writes on cancel/crash** with idempotent rerun in exchange for not holding all bodies in RAM until a single atomic commit (no DB transaction for files).

---

## Alternatives considered

1. **Raise / bypass `MAX_CONTEXT_CHARS` for chip PDFs** — exposes full extract to every Hermes turn; hides nothing; fights locked policy. Rejected: wrong boundary.
2. **`content.extract` then model `project.write_file` loop** — public surface looks familiar but dumps complexity onto the caller (model must hold bodies, name files, retry truncation). Interface depth is shallow: extract returns `text`. Rejected for this feature.
3. **MainWindow-only keyword dump with no control action** — hides the capability from Hermes/MCP re-entry and tests; concentrates PDF logic in the wrong layer. Rejected: grounding asked for a small pure module + thin UI hook; seat B requires a named action.

---

## Open questions and risks

- Should preflight **always** skip Hermes on clear intent, or always run Hermes after dump with the summary injected so the model can narrate?
- Is default extension always `.py`, or should labels like `7-5.cpp` / language hints in the PDF drive `filename`?
- For scanned PDFs, do we pass `vision_all=True` into `read_pdf_pages` for lab dump (costly) or keep `VISION_PAGE_CAP` and accept possible misses — which failure mode is preferred?
- How should dump interact with an already-truncated AttachmentWorker result mid-turn — cancel prepare, or race and ignore attachment text?
- Overwrite policy when on-disk file differs from newly parsed body: skip, overwrite, or write `7-5 (2).py`?

---

## Next implementation step

Add `iris/knowledge/lab_script_dump.py` with `LabProgram` / `LabDumpResult` / `LabDumpSummary`, `parse_lab_programs` + `to_hermes_summary` unit self-check (no PDF I/O), then wire `content.dump_lab_scripts` to call `dump_lab_scripts_from_pdf` and assert the tool payload has no `body` / `text` keys.
