"""U06 — partial read, name/content search, apply_patch with conflict detection.

stdlib-only. Hermes ``*** Begin Patch`` and unified-diff ``---/+++/@@`` shapes.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from iris.runtime.attachment_context import EXCLUDED, _is_link
from iris.system.execution_policy import check_path_allowed
from iris.system.patch_buffer_sync import (
    collect_open_buffer_conflicts,
    get_patch_buffer_sync,
    idle_ide_refresh,
    notify_files_patched,
)

SearchMode = Literal["content", "name"]

_MAX_READ_BYTES = 1_048_576
_MAX_SEARCH_ENTRIES = 20_000
_MAX_CONTENT_FILE_BYTES = 256_000

_BEGIN = "*** Begin Patch"
_END = "*** End Patch"
_UPDATE_FILE = "*** Update File:"
_ADD_FILE = "*** Add File:"
_DELETE_FILE = "*** Delete File:"
_TMP_SUFFIX = ".iris-patch-tmp"


@dataclass(frozen=True)
class _Hunk:
    old_lines: list[str]  # exact old slice including newlines where present
    new_lines: list[str]


@dataclass(frozen=True)
class _FileOp:
    path: str
    kind: Literal["update", "add", "delete"]
    hunks: list[_Hunk]


@dataclass(frozen=True)
class _Prepared:
    op: _FileOp
    abs_path: Path
    new_bytes: bytes | None  # None => delete
    snapshot: bytes | None  # None => file did not exist (add)
    snapshot_sha: str
    snapshot_mtime_ns: int


def read_text_range(
    path: str | Path,
    start_line: int | None = None,
    end_line: int | None = None,
    max_bytes: int = _MAX_READ_BYTES,
) -> dict[str, Any]:
    """Read UTF-8 text with optional 1-based inclusive line range.

    ``truncated`` is True when max_bytes cut the payload (or line slice still exceeds it).
    """
    target = Path(path).expanduser()
    if not target.is_file():
        raise FileNotFoundError(str(target))
    limit = max(1, int(max_bytes or _MAX_READ_BYTES))
    raw = target.read_bytes()
    if b"\x00" in raw:
        raise ValueError("not UTF-8 text")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8 text") from exc

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)
    start = 1 if start_line is None else max(1, int(start_line))
    end = total_lines if end_line is None else max(start, int(end_line))
    sliced = lines[start - 1 : end]
    body = "".join(sliced)
    truncated = False
    encoded = body.encode("utf-8")
    if len(encoded) > limit:
        truncated = True
        body = encoded[:limit].decode("utf-8", errors="ignore")
    elif start_line is None and end_line is None and len(raw) > limit:
        truncated = True
        body = raw[:limit].decode("utf-8", errors="ignore")
        start, end = 1, body.count("\n") + (0 if body.endswith("\n") else 1)

    return {
        "path": str(target),
        "content": body,
        "start_line": start,
        "end_line": end,
        "total_lines": total_lines,
        "bytes": len(body.encode("utf-8")),
        "truncated": truncated,
        "encoding": "utf-8",
    }


def search_files(
    root: str | Path,
    query: str,
    *,
    mode: SearchMode = "content",
    limit: int = 50,
) -> dict[str, Any]:
    """Search under root. ``mode=name`` matches relative path; ``mode=content`` matches file text."""
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    q = str(query or "").strip().casefold()
    if not q:
        raise ValueError("query required")
    mode_key: SearchMode = "name" if str(mode or "").strip().lower() == "name" else "content"
    cap = max(1, min(int(limit or 50), 200))
    matches: list[str] = []
    visited = 0
    truncated = False
    for directory, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d.casefold() not in EXCLUDED and not _is_link(Path(directory) / d)
        )
        for name in sorted(files):
            visited += 1
            if visited > _MAX_SEARCH_ENTRIES:
                truncated = True
                break
            candidate = Path(directory) / name
            if _is_link(candidate):
                continue
            relative = candidate.relative_to(base).as_posix()
            hit = False
            if mode_key == "name":
                hit = q in relative.casefold()
            else:
                try:
                    size = candidate.stat().st_size
                except OSError:
                    continue
                if size > _MAX_CONTENT_FILE_BYTES:
                    continue
                try:
                    data = candidate.read_bytes()
                except OSError:
                    continue
                if b"\x00" in data:
                    continue
                hit = q in data.decode("utf-8", errors="ignore").casefold()
            if hit:
                matches.append(relative)
                if len(matches) >= cap:
                    truncated = True
                    break
        if truncated:
            break
    return {
        "root": str(base),
        "query": query,
        "mode": mode_key,
        "matches": matches,
        "count": len(matches),
        "truncated": truncated,
    }


def _fingerprint(path: Path) -> tuple[str, int]:
    data = path.read_bytes() if path.is_file() else b""
    return hashlib.sha256(data).hexdigest(), (path.stat().st_mtime_ns if path.is_file() else 0)


def _detect_newline(raw: bytes) -> bytes:
    if b"\r\n" in raw:
        return b"\r\n"
    if b"\r" in raw and b"\n" not in raw:
        return b"\r"
    return b"\n"


def _detect_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _decode_text(raw: bytes) -> tuple[str, str, bytes]:
    """Return (text_with_lf, encoding, newline_bytes)."""
    encoding = _detect_encoding(raw)
    newline = _detect_newline(raw)
    text = raw.decode(encoding)
    # Hunk matching always uses \\n line endings.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, encoding, newline


def _encode_preserving(text: str, encoding: str, newline: bytes) -> bytes:
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == b"\r\n":
        body = body.replace("\n", "\r\n")
    elif newline == b"\r":
        body = body.replace("\n", "\r")
    return body.encode(encoding)


def _tmp_path_for(target: Path) -> Path:
    return target.with_name(target.name + _TMP_SUFFIX)


def _cleanup_tmp(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _restore_snapshot(abs_path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        _cleanup_tmp(abs_path)
        if abs_path.is_file():
            try:
                abs_path.unlink()
            except OSError:
                pass
        return
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(
        prefix=abs_path.name + ".",
        suffix=_TMP_SUFFIX,
        dir=str(abs_path.parent),
    )
    tmp = Path(raw_tmp)
    try:
        os.write(fd, snapshot)
        os.close(fd)
        fd = -1
        os.replace(str(tmp), str(abs_path))
    except Exception:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        _cleanup_tmp(tmp)
        raise


def _parse_hermes_ops(text: str) -> list[_FileOp]:
    lines = text.splitlines()
    ops: list[_FileOp] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\r")
        if line.startswith(_UPDATE_FILE) or line.startswith(_ADD_FILE) or line.startswith(_DELETE_FILE):
            if line.startswith(_UPDATE_FILE):
                kind: Literal["update", "add", "delete"] = "update"
                path = line[len(_UPDATE_FILE) :].strip()
            elif line.startswith(_ADD_FILE):
                kind = "add"
                path = line[len(_ADD_FILE) :].strip()
            else:
                kind = "delete"
                path = line[len(_DELETE_FILE) :].strip()
            i += 1
            hunks: list[_Hunk] = []
            while i < len(lines):
                cur = lines[i].rstrip("\r")
                if cur.startswith("*** ") and not cur.startswith("@@"):
                    break
                if cur.startswith("@@"):
                    i += 1
                    old_lines: list[str] = []
                    new_lines: list[str] = []
                    while i < len(lines):
                        row = lines[i].rstrip("\r")
                        if row.startswith("@@") or row.startswith("*** "):
                            break
                        if row.startswith("-"):
                            old_lines.append(row[1:] + "\n")
                        elif row.startswith("+"):
                            new_lines.append(row[1:] + "\n")
                        elif row.startswith(" "):
                            old_lines.append(row[1:] + "\n")
                            new_lines.append(row[1:] + "\n")
                        elif row == "":
                            old_lines.append("\n")
                            new_lines.append("\n")
                        else:
                            # bare context without leading space (tolerant)
                            old_lines.append(row + "\n")
                            new_lines.append(row + "\n")
                        i += 1
                    hunks.append(_Hunk(old_lines=old_lines, new_lines=new_lines))
                    continue
                i += 1
            ops.append(_FileOp(path=path.replace("\\", "/"), kind=kind, hunks=hunks))
            continue
        i += 1
    return ops


def _parse_unified_ops(text: str) -> list[_FileOp]:
    ops: list[_FileOp] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            old_path = line[4:].strip()
            if old_path.startswith("a/"):
                old_path = old_path[2:]
            i += 1
            if i >= len(lines) or not lines[i].startswith("+++ "):
                continue
            new_path = lines[i][4:].strip()
            if new_path.startswith("b/"):
                new_path = new_path[2:]
            path = (new_path if new_path not in ("/dev/null",) else old_path).replace("\\", "/")
            i += 1
            hunks: list[_Hunk] = []
            while i < len(lines) and lines[i].startswith("@@"):
                i += 1
                old_lines: list[str] = []
                new_lines: list[str] = []
                while i < len(lines):
                    row = lines[i]
                    if row.startswith("@@") or row.startswith("--- "):
                        break
                    if row.startswith("\\"):  # "\ No newline at end of file"
                        i += 1
                        continue
                    if row.startswith("-"):
                        old_lines.append(row[1:] + "\n")
                    elif row.startswith("+"):
                        new_lines.append(row[1:] + "\n")
                    elif row.startswith(" "):
                        old_lines.append(row[1:] + "\n")
                        new_lines.append(row[1:] + "\n")
                    else:
                        old_lines.append(row + "\n")
                        new_lines.append(row + "\n")
                    i += 1
                hunks.append(_Hunk(old_lines=old_lines, new_lines=new_lines))
            kind: Literal["update", "add", "delete"] = "update"
            if old_path in ("/dev/null",):
                kind = "add"
            elif new_path in ("/dev/null",):
                kind = "delete"
            ops.append(_FileOp(path=path, kind=kind, hunks=hunks))
            continue
        i += 1
    return ops


def parse_patch(patch_text: str) -> list[_FileOp]:
    text = str(patch_text or "")
    if _BEGIN in text or _UPDATE_FILE in text or _ADD_FILE in text:
        body = text
        if _BEGIN in body:
            start = body.find(_BEGIN) + len(_BEGIN)
            end = body.find(_END)
            body = body[start:] if end < 0 else body[start:end]
        ops = _parse_hermes_ops(body)
        if ops:
            return ops
    return _parse_unified_ops(text)


def _apply_hunks(original: str, hunks: list[_Hunk]) -> tuple[str | None, str | None]:
    """Return (new_text, conflict_reason)."""
    text = original
    # Normalize to newline-terminated lines for matching.
    if text and not text.endswith("\n"):
        # keep exact; matching uses \n-suffixed hunk lines
        pass
    for hunk in hunks:
        old = "".join(hunk.old_lines)
        new = "".join(hunk.new_lines)
        if not old:
            # pure insert at EOF when no context
            text = text + new
            continue
        idx = text.find(old)
        if idx < 0:
            # tolerate missing final newline on last old line
            alt_old = old[:-1] if old.endswith("\n") else old + "\n"
            idx = text.find(alt_old)
            if idx < 0:
                return None, "expected context missing"
            old = alt_old
            if new.endswith("\n") and not text[idx : idx + len(old)].endswith("\n"):
                new = new[:-1]
        text = text[:idx] + new + text[idx + len(old) :]
    return text, None


def _fingerprint_conflict(
    op_path: str,
    sha: str,
    mtime_ns: int,
    expected_sha256: dict[str, str] | None,
    expected_mtime_ns: dict[str, int] | None,
) -> str | None:
    exp_sha = (expected_sha256 or {}).get(op_path)
    if exp_sha is not None and exp_sha != sha:
        return "disk sha256 mismatch (unsaved/concurrent)"
    exp_mtime = (expected_mtime_ns or {}).get(op_path)
    if exp_mtime is not None and int(exp_mtime) != int(mtime_ns):
        return "disk mtime mismatch (unsaved/concurrent)"
    return None


def apply_patch(
    root: str | Path,
    patch_text: str,
    *,
    expected_sha256: dict[str, str] | None = None,
    expected_mtime_ns: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Apply patch under root as one transaction.

    Snapshot fingerprints → plan → write temps → re-verify → atomic replace.
    On any commit failure, restore snapshots for already-replaced files.
    Optional expected sha256/mtime refuse dirty/concurrent overwrite (including delete).
    Newline style and encoding of existing files are preserved.
    """
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise NotADirectoryError(str(base))
    ops = parse_patch(patch_text)
    idle_refresh = idle_ide_refresh()
    ok_note_stub = (
        "disk updated; IDE buffer hook absent — editor buffers not synced"
    )
    conflict_note = "disk not updated on conflict"
    if not ops:
        return {
            "ok": False,
            "conflicts": [{"path": "", "reason": "empty or unparseable patch"}],
            "files_changed": [],
            "ide_refresh": idle_refresh,
            "note": conflict_note,
        }

    conflicts: list[dict[str, Any]] = []
    prepared: list[_Prepared] = []

    for op in ops:
        decision = check_path_allowed(base, op.path, write=True)
        if not decision.allowed:
            conflicts.append({"path": op.path, "reason": decision.reason or "path not allowed"})
            continue
        abs_path = (base / op.path).resolve()
        if not str(os.path.normcase(str(abs_path))).startswith(
            os.path.normcase(str(base)) + os.sep
        ) and abs_path != base:
            conflicts.append({"path": op.path, "reason": "path escapes root"})
            continue

        if op.kind == "delete":
            if abs_path.is_file():
                sha, mtime_ns = _fingerprint(abs_path)
                reason = _fingerprint_conflict(
                    op.path, sha, mtime_ns, expected_sha256, expected_mtime_ns
                )
                if reason:
                    conflicts.append({"path": op.path, "reason": reason})
                    continue
                snapshot = abs_path.read_bytes()
            else:
                sha, mtime_ns, snapshot = "", 0, None
            prepared.append(
                _Prepared(
                    op=op,
                    abs_path=abs_path,
                    new_bytes=None,
                    snapshot=snapshot,
                    snapshot_sha=sha,
                    snapshot_mtime_ns=mtime_ns,
                )
            )
            continue

        if op.kind == "add":
            if abs_path.exists():
                conflicts.append({"path": op.path, "reason": "file already exists"})
                continue
            new_text, reason = _apply_hunks("", op.hunks)
            if reason:
                conflicts.append({"path": op.path, "reason": reason})
                continue
            new_bytes = _encode_preserving(new_text or "", "utf-8", b"\n")
            prepared.append(
                _Prepared(
                    op=op,
                    abs_path=abs_path,
                    new_bytes=new_bytes,
                    snapshot=None,
                    snapshot_sha="",
                    snapshot_mtime_ns=0,
                )
            )
            continue

        if not abs_path.is_file():
            conflicts.append({"path": op.path, "reason": "file missing"})
            continue

        sha, mtime_ns = _fingerprint(abs_path)
        reason = _fingerprint_conflict(
            op.path, sha, mtime_ns, expected_sha256, expected_mtime_ns
        )
        if reason:
            conflicts.append({"path": op.path, "reason": reason})
            continue

        raw = abs_path.read_bytes()
        original, encoding, newline = _decode_text(raw)
        new_text, reason = _apply_hunks(original, op.hunks)
        if reason:
            conflicts.append({"path": op.path, "reason": reason})
            continue
        sha2, mtime2 = _fingerprint(abs_path)
        if sha2 != sha or mtime2 != mtime_ns:
            conflicts.append({"path": op.path, "reason": "disk changed during patch plan"})
            continue
        new_bytes = _encode_preserving(
            new_text if new_text is not None else original, encoding, newline
        )
        prepared.append(
            _Prepared(
                op=op,
                abs_path=abs_path,
                new_bytes=new_bytes,
                snapshot=raw,
                snapshot_sha=sha,
                snapshot_mtime_ns=mtime_ns,
            )
        )

    if conflicts:
        return {
            "ok": False,
            "conflicts": conflicts,
            "files_changed": [],
            "ide_refresh": idle_refresh,
            "note": conflict_note,
        }

    target_paths = [item.op.path for item in prepared]
    buffer_conflicts = collect_open_buffer_conflicts(str(base), target_paths)
    if buffer_conflicts:
        return {
            "ok": False,
            "conflicts": buffer_conflicts,
            "files_changed": [],
            "ide_refresh": "conflict" if get_patch_buffer_sync() is not None else "stub",
            "note": conflict_note,
        }

    # Stage temps for non-delete ops.
    temps: list[Path] = []
    try:
        for item in prepared:
            if item.new_bytes is None:
                continue
            item.abs_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = _tmp_path_for(item.abs_path)
            tmp.write_bytes(item.new_bytes)
            temps.append(tmp)

        committed: list[_Prepared] = []
        try:
            for item in prepared:
                if item.op.kind != "add" and item.snapshot is not None:
                    sha_now, mtime_now = _fingerprint(item.abs_path)
                    if sha_now != item.snapshot_sha or mtime_now != item.snapshot_mtime_ns:
                        raise OSError("disk changed before atomic replace")
                if item.new_bytes is None:
                    if item.abs_path.is_file():
                        item.abs_path.unlink()
                    committed.append(item)
                    continue
                tmp = _tmp_path_for(item.abs_path)
                os.replace(str(tmp), str(item.abs_path))
                if tmp in temps:
                    temps.remove(tmp)
                committed.append(item)
        except OSError as exc:
            for done in reversed(committed):
                try:
                    _restore_snapshot(done.abs_path, done.snapshot)
                except OSError:
                    pass
            for tmp in temps:
                _cleanup_tmp(tmp)
            return {
                "ok": False,
                "conflicts": [{"path": "", "reason": f"apply failed: {exc}"}],
                "files_changed": [],
                "ide_refresh": idle_refresh,
                "note": conflict_note,
            }
    except OSError as exc:
        for tmp in temps:
            _cleanup_tmp(tmp)
        return {
            "ok": False,
            "conflicts": [{"path": "", "reason": f"stage failed: {exc}"}],
            "files_changed": [],
            "ide_refresh": idle_refresh,
            "note": conflict_note,
        }

    for tmp in temps:
        _cleanup_tmp(tmp)

    changed = [item.op.path for item in prepared]
    refresh = notify_files_patched(str(base), changed)
    if refresh is None:
        ide_refresh = idle_ide_refresh()
        note = ok_note_stub
    else:
        ide_refresh = refresh
        note = {
            "ok": "disk updated; IDE buffers reloaded from disk",
            "conflict": "disk updated; IDE refused reload (dirty open buffer)",
            "unavailable": "disk updated; IDE buffer sync unavailable",
            "stub": ok_note_stub,
        }.get(ide_refresh, "disk updated; IDE buffer sync status unknown")
    return {
        "ok": True,
        "conflicts": [],
        "files_changed": changed,
        "ide_refresh": ide_refresh,
        "note": note,
    }
