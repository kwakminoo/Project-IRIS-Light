# Candidate A — App-owned intercept (chip PDF lab dump)

Seat: architect arena runner A  
Direction: detect lab-dump intent in the app shell; extract+parse+write without stuffing PDF into Hermes 24k messages.  
Status: sketch only — bodies raise `NotImplementedError`. No production fill-in in this package.

---

## Problem

칩 PDF + 「실습 스크립트 전부 만들어」 요청이 지금 `AttachmentWorker` → `prepare_attachments`(예산 `MAX_CONTEXT_CHARS` 24k) → Hermes로 간다. 잘리면 `truncated=true` 부분 본문만 모델에 들어가고, Hermes는 붙여넣기를 요구하거나 일부 실습만 만든다. 전역 한도(`MAX_FILE_BYTES` 20MB, `MAX_CONTEXT_CHARS` 24k, `MAX_PDF_PAGES` 200, `VISION_PAGE_CAP` 4, `content_extract._MAX_CHARS` 80k)는 유지해야 하고, 모델에게 PyMuPDF를 돌리게 하거나 IDE PDF 뷰어를 새로 두지 않는다. 기존 로컬 우회(`_try_local_pdf_save`, `wiki_save_intent`)처럼 **앱이 소유한 의도 감지 + 순수 모듈 dump + `write_project_file`** 이 맞다. 비명백한 점: AttachmentWorker 이후 prepared를 버릴지, Worker 자체를 건너뛸지 — 이 후보는 **의도 일치 시 Worker/Hermes를 모두 건너뛰는 앱 인터셉트**를 택한다.

## Usage (caller's view)

### README (소비자: MainWindow 턴 셸)

1. 사용자 텍스트 + 칩 PDF 경로가 있으면 `is_lab_dump_intent(text)` 로 이 턴이 「전 실습 파일 덤프」인지 판별한다.
2. 맞으면 `LabDumpWorker`로 `dump_lab_scripts(pdf, project_root)` 를 돌린다. `prepare_attachments` / `PreparedAttachments.model_content` / Hermes 메시지에 PDF 본문을 넣지 않는다.
3. 완료 슬롯에서 `format_lab_dump_reply(result)` 문자열만 채팅·히스토리에 넣고 `_finish_current_turn(..., open_followup=False)` 한다.
4. 의도가 아니면 `None`/False — 기존 AttachmentWorker → Hermes 경로 그대로.

### Call site 1 — early intercept (preferred, mirrors `_try_local_pdf_save`)

```python
# iris/ui/window/main_window.py  — before AttachmentWorker arm
def _try_local_lab_dump(self, turn: UserTurn) -> bool:
    from iris.knowledge.lab_script_dump import is_lab_dump_intent, pdf_paths_from
    from iris.ui.workers.lab_dump_worker import LabDumpWorker

    pdfs = pdf_paths_from(turn.attachments)
    if not is_lab_dump_intent(turn.text or "", pdfs):
        return False
    root = self._current_project_root()
    if not root:
        self._chat.append_message_instant("Iris", "프로젝트를 연 뒤 다시 요청해 주세요.")
        self._finish_current_turn(turn.id, open_followup=False)
        return True
    self._present_user_turn_early(turn)
    self._record_history("user", self._format_user_turn_content(turn))
    self._chat.append_message_instant("Iris", "실습 스크립트를 PDF에서 추출해 저장하는 중…")
    self._chat.set_generating(True)
    worker = LabDumpWorker(
        pdfs[0], root, query=turn.text or "",
        image_reader=self._material_vision_reader(model),  # optional OCR/vision
        parent=self,
    )
    worker.finished_ok.connect(lambda reply, tid=turn.id: self._on_lab_dump_ok(tid, reply))
    worker.finished_err.connect(lambda err, tid=turn.id: self._on_lab_dump_err(tid, err))
    self._lab_dump_worker = worker
    worker.start()
    return True  # Hermes skipped
```

### Call site 2 — pure dump (worker / tests)

```python
from pathlib import Path
from iris.knowledge.lab_script_dump import dump_lab_scripts, format_lab_dump_reply

result = dump_lab_scripts(
    Path(r"C:\chip\lecture.pdf"),
    Path(r"C:\proj"),
    page_limit=200,          # MAX_PDF_PAGES — do not raise
    out_subdir="labs",
)
reply = format_lab_dump_reply(result)
# reply.user_visible → "저장함:\n- labs/7-5.py\n- labs/7-7.py\n…"
# result.written → ("labs/7-5.py", …); never pass page bodies to Hermes
```

### Call site 3 — unit parse without I/O

```python
from iris.knowledge.lab_script_dump import parse_lab_programs, filename_for_label

pages = ["[쪽 1]\n프로그램 7-5\nprint(1)\n", "[쪽 2]\n프로그램 7-7\nx=1\n"]
programs = parse_lab_programs(pages)
assert programs[0].filename == filename_for_label(programs[0].label)
# programs[0].body stays in-process; write_project_file only at dump boundary
```

---

## Types

```python
# iris/knowledge/lab_script_dump.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

# Re-export policy constants by import, do not redefine:
#   attachment_context.MAX_PDF_PAGES, MAX_FILE_BYTES
#   content_extract.VISION_PAGE_CAP  (used only when vision_reader provided)


@dataclass(frozen=True)
class LabProgram:
    """One practice block carved from PDF page text."""

    label: str                 # e.g. "7-5", "프로그램 7-7"
    filename: str              # e.g. "7-5.py" — derived, never free-form from model
    body: str                  # source text to write (may be empty → error at write)
    pages: tuple[int, ...]     # 1-based page numbers that contributed


@dataclass(frozen=True)
class LabDumpResult:
    """Outcome of one dump operation. Idempotent re-run overwrites same rel paths."""

    programs: tuple[LabProgram, ...]
    written: tuple[str, ...]   # project-relative paths successfully written
    errors: tuple[str, ...]    # per-program or extract failures (user-visible lines)
    truncated_pages: bool      # True if PDF had more pages than page_limit
    source_pdf: str = ""       # absolute path used (host-only; not for Hermes stuffing)


@dataclass(frozen=True)
class LabDumpReply:
    """Thin UI payload: path list only. Invariant: no PDF page body in user_visible."""

    user_visible: str
    written_rel_paths: tuple[str, ...]
    had_errors: bool


# Vision hook matches AttachmentWorker image_reader shape (bytes → text).
VisionReader = Callable[[bytes], str]
```

Invariants encoded in types:

- `LabProgram.filename` is produced only by `filename_for_label` (single source).
- `LabDumpReply` does not carry `programs` bodies — UI cannot accidentally paste extract into Hermes.
- `pages` is a tuple (immutable) so results are shareable across threads without copy.

---

## Signatures (`raise NotImplementedError`)

```python
def is_lab_dump_intent(text: str, pdf_paths: Sequence[str] = ()) -> bool:
    """True when user asks to materialize every lab/practice script from an attached PDF.

    Heuristic owns Korean/English cues (실습, 프로그램, 전부, 만들어, dump labs, …)
    plus presence of at least one .pdf path. False → caller must not enter dump path.
    """
    raise NotImplementedError


def pdf_paths_from(attachments: Sequence[str]) -> tuple[str, ...]:
    """Filter chip paths to existing .pdf files. Order preserved."""
    raise NotImplementedError


def filename_for_label(label: str) -> str:
    """Map PDF label → safe relative basename (e.g. '프로그램 7-7' → '7-7.py').

    Strip unsafe path chars; default extension .py for code labs.
    """
    raise NotImplementedError


def parse_lab_programs(page_texts: Sequence[str]) -> list[LabProgram]:
    """Split page texts (``[쪽 N]`` style or bare) into LabProgram list.

    Pure. No I/O. Empty input → []. Overlapping labels: last body wins at dump write.
    """
    raise NotImplementedError


def extract_pdf_page_texts(
    pdf_path: Path | str,
    *,
    page_limit: int | None = None,
    vision_reader: VisionReader | None = None,
) -> tuple[list[str], bool]:
    """Page-by-page extract via content_extract.read_pdf_pages (OCR hybrid).

    Returns (page_texts, truncated_pages). Does not apply MAX_CONTEXT_CHARS.
    Honors MAX_PDF_PAGES when page_limit is None. May use VISION_PAGE_CAP per
    read_pdf_pages policy when vision_reader is set — do not invent a second cap.
    """
    raise NotImplementedError


def dump_lab_scripts(
    pdf_path: Path | str,
    project_root: Path | str,
    *,
    page_limit: int | None = None,
    out_subdir: str = "labs",
    vision_reader: VisionReader | None = None,
) -> LabDumpResult:
    """Extract → parse → write_project_file for each program.

    # TODO: for each LabProgram, rel = posixpath.join(out_subdir, filename)
    # TODO: skip write if body empty → append to errors
    # TODO: write_project_file(root, rel, body); collect written / errors
    # Never returns PDF body for model stuffing.
    """
    raise NotImplementedError


def format_lab_dump_reply(result: LabDumpResult) -> LabDumpReply:
    """Build short Iris reply: written path bullets + error lines. No code bodies."""
    raise NotImplementedError


def try_handle_lab_dump(
    text: str,
    attachments: Sequence[str],
    project_root: str,
    *,
    vision_reader: VisionReader | None = None,
    out_subdir: str = "labs",
) -> LabDumpReply | None:
    """Facade for non-Qt callers/tests.

    None if not lab-dump intent or no PDF. Else dump first PDF and return reply.
    MainWindow prefers LabDumpWorker + dump_lab_scripts; this stays for CLI/checks.
    """
    raise NotImplementedError
```

### Worker shell (thin Qt adapter)

```python
# iris/ui/workers/lab_dump_worker.py
from PyQt6.QtCore import QThread, pyqtSignal

class LabDumpWorker(QThread):
    finished_ok = pyqtSignal(object)   # LabDumpReply
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        pdf_path: str,
        project_root: str,
        *,
        query: str = "",
        out_subdir: str = "labs",
        image_reader=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.project_root = project_root
        self.query = query
        self.out_subdir = out_subdir
        self.image_reader = image_reader

    def run(self) -> None:
        # TODO: call dump_lab_scripts + format_lab_dump_reply; emit ok/err
        # Never call prepare_attachments.
        raise NotImplementedError
```

### MainWindow hook signatures (sketch)

```python
# methods on MainWindow — bodies NotImplemented until Phase D
def _try_local_lab_dump(self, turn: "UserTurn") -> bool:
    """Return True if this turn is fully handled (Hermes must not run)."""
    raise NotImplementedError

def _on_lab_dump_ok(self, turn_id: str, reply: "LabDumpReply") -> None:
    raise NotImplementedError

def _on_lab_dump_err(self, turn_id: str, err: str) -> None:
    raise NotImplementedError
```

Wire `_try_local_lab_dump(turn)` in the same early-local chain as `_try_local_pdf_save` / wiki save — **before** `AttachmentWorker` is armed. If True, return without `prepare_attachments`.

---

## Module map

```
iris/knowledge/lab_script_dump.py     # OWN: intent, parse, extract glue, dump, reply
                                      # USES: content_extract.read_pdf_pages,
                                      #       project_ops.write_project_file,
                                      #       attachment_context.MAX_PDF_PAGES (import)

iris/ui/workers/lab_dump_worker.py    # OWN: QThread boundary only
                                      # USES: lab_script_dump.dump_lab_scripts,
                                      #       format_lab_dump_reply

iris/ui/window/main_window.py         # OWN: when to intercept + chat/history/finish
                                      # USES: is_lab_dump_intent, LabDumpWorker
                                      # MUST NOT: prepared.model_content on this path

iris/ui/_check_lab_script_dump.py     # OWN: intent + parse + dump self-check (no Hermes)

# Unchanged owners (called, not forked):
iris/knowledge/content_extract.py     # read_pdf_pages, VISION_PAGE_CAP, _MAX_CHARS
iris/runtime/attachment_context.py    # MAX_* globals stay; prepare_attachments unused here
iris/system/project_ops.py            # write_project_file
```

Call chain length (happy path): **MainWindow → LabDumpWorker → lab_script_dump.dump_lab_scripts → write_project_file**. Three hops. No Hermes.

Data flow:

```
chip PDF path + user text
  → is_lab_dump_intent? ─no─→ AttachmentWorker → Hermes (unchanged)
         │ yes
         ▼
  LabDumpWorker
         ▼
  extract_pdf_page_texts (page-by-page, ≤ MAX_PDF_PAGES)
         ▼
  parse_lab_programs → list[LabProgram]
         ▼
  write_project_file(root, labs/<filename>, body) × N
         ▼
  LabDumpReply (paths only) → chat + history → finish turn
```

---

## Shape

**Architecture:** one deep knowledge module owns “what is a lab dump and how files appear on disk”; MainWindow only decides *whether* this turn is that job; worker only moves blocking I/O off the GUI thread. Pattern matches `_try_local_pdf_save` + `PdfExportWorker` (app-owned intercept), not a new Hermes tool.

**Load-bearing decisions:**

1. **Intercept before AttachmentWorker** — never spend 24k prepare budget on a turn that will not send extract to the model. Seat phrase “after AttachmentWorker / instead of sending prepared” is satisfied by skipping send entirely; preferred cut is earlier to avoid wasted work.
2. **Hermes optional/skipped** — successful intercept finishes the turn locally. No short “summary for model” round-trip required (policy allows skip).
3. **`write_project_file` is the only writer** — same path resolution/UTF-8 contract as project tools; no ad-hoc `Path.write_text` in UI.
4. **Globals stay imported constants** — dump path must not raise or redefine `MAX_CONTEXT_CHARS`; it simply does not use that budget for messages. Page extract still capped by `MAX_PDF_PAGES` / existing `read_pdf_pages` vision policy.
5. **Default `out_subdir="labs"`** — clear project folder; empty subdir allowed later if product wants root-flat names like `7-5.py`.

**Interface depth:** public surface is `is_lab_dump_intent` + `dump_lab_scripts` (+ thin worker). Callers do not see page OCR stages, label regexes, or truncate policy. Exposed: intent bool, paths, reply string. Hidden: extract hybrid, parse, write loop, error aggregation — per boundary-discipline and deep-module preference.

**Deliberately does not:** remove global limits; open PDF in IDE; ask Hermes to call content.extract; add a MainWindow boolean flag for “lab mode”; put program bodies in chat history.

## Synthesis decision

*(Arena fills this. Candidate A base claim: app-owned early intercept + pure `lab_script_dump` module; Hermes skipped.)*

## Tradeoffs accepted

- We accept **false-positive intercepts** (user meant “설명만”) in exchange for **never truncating dump through 24k** — mitigate with tight intent lexicon + require PDF attachment.
- We accept **dumping only the first PDF** when multiple chips attach in exchange for a **single clear writer path** (no merge UI).
- We accept **re-extract inside LabDumpWorker** (possibly repeating OCR AttachmentWorker would have done) in exchange for **not coupling dump to PreparedAttachments**.
- We accept **fixed Iris prose reply** (no LLM polish) in exchange for **deterministic path list and zero model stuffing**.
- We accept **`labs/` subfolder default** in exchange for **not colliding with existing project files at root**.

## Alternatives considered

1. **Post-AttachmentWorker gate in `_continue_user_turn_bound`** — still run `prepare_attachments`, then ignore `model_content` and dump from path. Exposes callers to truncated notices and wasted 24k work; hides little. Rejected for seat A: weaker “bypass stuffing” story.
2. **Hermes tool `lab.dump` after short metadata-only message** — model chooses when to dump. Exposes tool protocol and trust to the agent; hides extract complexity but **fails the locked policy** that the lab-dump path must not depend on model stuffing/tools for the full extract. Rejected.
3. **Boolean / branch inside `prepare_attachments`** — temporal decomposition and split ownership of “chat excerpt” vs “full dump”. Callers learn internal prepare stages. Rejected; keep prepare chat-only.

## Open questions and risks

- Should intent fire on 「7-7만 만들어」 (single lab) or only 「전부/모든 실습」? Single-lab might still want app dump of one label — scope?
- OCR-heavy scanned PDFs: `vision_all=True` vs default `VISION_PAGE_CAP` — dump completeness vs runtime; product default?
- Overwrite policy when `labs/7-5.py` already exists — always overwrite (idempotent) or skip with error line?
- If no project root is open, write under `~/Documents/IRIS/labs` or refuse?
- Label patterns beyond `프로그램 N-M` / `N-M.py` — lecture-specific headings?

## Next implementation step

Add `iris/knowledge/lab_script_dump.py` with the dataclasses and `raise NotImplementedError` stubs above, plus `iris/ui/_check_lab_script_dump.py` that imports the public names and asserts `is_lab_dump_intent` / `parse_lab_programs` exist — then fill parse+dump against a tiny fixture PDF text.

---

## Red-flag screen (pre-synthesis)

| Flag | Status |
|------|--------|
| Shallow module | Pass — one dump facade hides extract/parse/write |
| Information leakage | Pass — no PreparedAttachments / wire types on public API |
| Temporal decomposition | Pass — knowledge grouped in `lab_script_dump`, not load/parse/save packages |
| Pass-through | Pass — worker adds thread policy only |
| Split ownership | Pass — only `write_project_file` writes; module owns parse rules |
| Two ways | Pass — single intercept; Hermes path untouched when intent false |
| Importable internals | Mitigate in fill-in: keep `_LABEL_RE` private with leading underscore |
| Hand-synced list | Pass — filenames derived from labels via `filename_for_label` |
