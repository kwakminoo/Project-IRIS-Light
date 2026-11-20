"""채팅 내용을 PDF로 저장.

생성은 자식 프로세스에서만 한다. PyMuPDF가 Qt 프로세스 안에서 abort 하면
IRIS 전체가 죽으므로, 실패·네이티브 크래시는 자식으로 가두고 메시지만 돌린다.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_PDF_WORD = re.compile(r"pdf", re.IGNORECASE)
_MAKE_WORDS = ("저장", "만들", "변환", "뽑아", "export", "save")
_WIKI_WORDS = ("위키", "wiki", "obsidian", "옵시디언")
_WIN_PDF = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\)[^\r\n<>\"']+?\.pdf",
    re.IGNORECASE,
)
_NAMED_PDF = re.compile(r"([^\s\\/:*?\"<>|]+\.pdf)", re.IGNORECASE)


def trace(msg: str) -> None:
    """PDF·앱 종료 진단. pythonw여도 ~/.iris-light/logs/pdf.log 에 남긴다."""
    text = str(msg)
    try:
        print(text, flush=True)
    except Exception:
        pass
    try:
        log_dir = Path.home() / ".iris-light" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "pdf.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%H:%M:%S')} {text}\n")
    except Exception:
        pass


def is_pdf_save_intent(text: str) -> bool:
    """위키 저장이 아닌 'PDF로 저장/만들어' 요청."""
    raw = text or ""
    if not _PDF_WORD.search(raw):
        return False
    low = raw.lower()
    if any(w in low for w in _WIKI_WORDS):
        return False
    return any(w in raw or w in low for w in _MAKE_WORDS)


def output_path_for(text: str) -> Path:
    """요청 문장의 경로·파일명. 없으면 Documents/IRIS/iris-note.pdf."""
    raw = text or ""
    found = _WIN_PDF.search(raw)
    if found:
        return Path(found.group(0).strip().strip('"').strip("'"))
    named = _NAMED_PDF.search(raw)
    base = Path.home() / "Documents" / "IRIS"
    if named:
        return base / Path(named.group(1)).name
    return base / "iris-note.pdf"


def _cjk_font() -> str | None:
    candidates = (
        Path(r"C:\Windows\Fonts\malgun.ttf"),
        Path(r"C:\Windows\Fonts\malgunsl.ttf"),
        Path(r"C:\Windows\Fonts\gulim.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/Library/Fonts/AppleGothic.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def write_pdf_file(text: str, dest: Path) -> None:
    """자식 프로세스 전용. 호출측 IRIS 프로세스에서 직접 부르지 말 것."""
    import pymupdf

    body = (text or "").strip()
    if not body:
        raise ValueError("저장할 내용이 없습니다.")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.is_dir():
        raise OSError(f"저장 경로가 폴더입니다: {dest}")

    font_file = _cjk_font()
    font = pymupdf.Font(fontfile=font_file) if font_file else pymupdf.Font("helv")
    doc = pymupdf.open()
    try:
        remaining = body
        pages = 0
        while remaining.strip() and pages < 200:
            page = doc.new_page()
            rect = pymupdf.Rect(50, 48, page.rect.width - 50, page.rect.height - 48)
            writer = pymupdf.TextWriter(page.rect)
            leftover = writer.fill_textbox(rect, remaining, font=font, fontsize=11)
            writer.write_text(page)
            pages += 1
            if not leftover:
                remaining = ""
                break
            remaining = "\n".join(str(item[0]) for item in leftover if item)
            if remaining.strip() == body.strip():
                break
            body = remaining
        if pages == 0:
            raise ValueError("PDF 페이지를 만들지 못했습니다.")
        doc.subset_fonts()
        doc.save(str(dest), garbage=4, deflate=True)
    finally:
        doc.close()
    trace("[PDF] file closed")
    if not dest.is_file() or dest.stat().st_size < 64:
        raise OSError("PDF 파일이 생성되지 않았습니다.")


def verify_pdf_file(path: Path) -> dict[str, str | bool | int]:
    """V step: verify the resolved file produced by the real PDF path."""
    target = Path(path).expanduser().resolve()
    try:
        size = target.stat().st_size
        if size < 64:
            raise ValueError("PDF is too small")
        with target.open("rb") as handle:
            head = handle.read(5)
            handle.seek(max(0, size - 1024))
            tail = handle.read()
        if head != b"%PDF-" or b"%%EOF" not in tail:
            raise ValueError("invalid PDF signature")
        return {"ok": True, "path": str(target), "size": size, "error": ""}
    except (OSError, ValueError) as exc:
        return {"ok": False, "path": str(target), "size": 0, "error": str(exc)}


def _failure(detail: str) -> dict[str, str | bool]:
    text = (detail or "알 수 없는 오류").strip()
    if "접근" in text or "Permission" in text or "WinError 5" in text:
        text = f"저장 경로에 접근할 수 없습니다. {text}"
    return {"ok": False, "path": "", "error": f"PDF 저장에 실패했습니다: {text}"}


def save_pdf(text: str, dest: Path, *, timeout_sec: float = 60.0) -> dict[str, str | bool]:
    """IRIS 쪽에서 호출. 자식이 죽어도 이 함수는 예외를 올리지 않는다."""
    dest = Path(dest).expanduser()
    trace("[PDF] generation started")
    trace(f"[PDF] file path: {dest}")
    if not (text or "").strip():
        fail = _failure("저장할 내용이 없습니다.")
        trace(f"[PDF] generation failed: {fail['error']}")
        return fail
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail = _failure(f"저장 경로에 접근할 수 없습니다. ({exc})")
        trace(f"[PDF] generation failed: {fail['error']}")
        return fail
    if any(ch in dest.name for ch in '<>:"|?*'):
        fail = _failure(f"파일명에 사용할 수 없는 문자가 있습니다: {dest.name}")
        trace(f"[PDF] generation failed: {fail['error']}")
        return fail

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".txt",
            prefix="iris-pdf-",
            delete=False,
        ) as handle:
            handle.write(text)
            tmp_path = handle.name
        from iris.system.win_subprocess import no_window_kwargs

        # 자식 abort/콘솔 이벤트가 IRIS 프로세스 그룹으로 올라오지 않게 분리.
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "iris.knowledge.pdf_export",
                "--text",
                tmp_path,
                "--out",
                str(dest),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_sec),
            check=False,
            **no_window_kwargs(
                extra_creationflags=int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            ),
        )
    except subprocess.TimeoutExpired:
        fail = _failure("생성 시간이 너무 깁니다.")
        trace(f"[PDF] generation failed: {fail['error']}")
        return fail
    except OSError as exc:
        fail = _failure(str(exc))
        trace(f"[PDF] generation failed: {fail['error']}")
        return fail
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if proc.returncode != 0 or not dest.is_file():
        if proc.returncode < 0 or proc.returncode > 255:
            detail = f"PDF 생성 프로세스가 비정상 종료되었습니다 (code {proc.returncode})."
        else:
            detail = (proc.stderr or proc.stdout or "PDF 생성에 실패했습니다.").strip()
        fail = _failure(detail.splitlines()[-1][:300] if detail else "PDF 생성에 실패했습니다.")
        trace(f"[PDF] generation failed: {fail['error']}")
        return fail
    verified = verify_pdf_file(dest)
    if not verified["ok"]:
        fail = _failure(str(verified["error"]))
        trace(f"[PDF] generation failed: {fail['error']}")
        return fail
    trace("[PDF] generation completed")
    return {
        "ok": True,
        "path": str(verified["path"]),
        "size": int(verified["size"]),
        "verified": True,
        "error": "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a text PDF (child process).")
    parser.add_argument("--text", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--abort", action="store_true")
    args = parser.parse_args(argv)
    if args.abort:
        os.abort()
    if not args.text or not args.out:
        print("text and out required", file=sys.stderr)
        return 2
    try:
        body = Path(args.text).read_text(encoding="utf-8")
        write_pdf_file(body, Path(args.out))
    except Exception as exc:  # noqa: BLE001 — 자식은 메시지만 남기고 죽는다
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
