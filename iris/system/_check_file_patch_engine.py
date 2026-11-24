"""U06 — File & Patch Engine.

Fails when:
- read_text_range lacks line range / truncation flag
- search_files does not distinguish name vs content mode
- apply_patch cannot apply a unified-diff / Hermes-style patch
- missing expected context does not conflict
- apply_patch overwrites when disk hash/mtime fingerprint drifted
- successful apply leaves .tmp junk beside targets
- multi-file mid-apply failure does not restore already-replaced files
- CRLF / encoding not preserved on rewrite
- delete ignores wrong expected fingerprint

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_file_patch_engine
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from iris.infrastructure.absorbed_tool_aliases import (
    model_names,
    resolve_action,
    strip_only_names,
)
from iris.infrastructure.speak_capability import PHASE4_ALLOWLIST
from iris.system.file_patch import apply_patch, read_text_range, search_files
from iris.system.patch_buffer_sync import (
    get_patch_buffer_sync,
    notify_files_patched,
    set_patch_buffer_sync,
)


def _write_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _check_read_range() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        path = root / "sample.txt"
        _write_lf(path, "a\nb\nc\nd\ne\n")
        out = read_text_range(path, start_line=2, end_line=4)
        assert out["content"] == "b\nc\nd\n", out
        assert out["truncated"] is False
        assert out["start_line"] == 2
        assert out["end_line"] == 4
        tiny = read_text_range(path, max_bytes=3)
        assert tiny["truncated"] is True
        assert len(tiny["content"].encode("utf-8")) <= 3


def _check_search_modes() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _write_lf(root / "alpha.txt", "hello world\n")
        _write_lf(root / "beta_hello.txt", "zzz\n")
        by_name = search_files(root, "hello", mode="name")
        assert "beta_hello.txt" in by_name["matches"]
        assert "alpha.txt" not in by_name["matches"]
        by_content = search_files(root, "hello", mode="content")
        assert "alpha.txt" in by_content["matches"]
        assert "beta_hello.txt" not in by_content["matches"]
        assert by_name["mode"] == "name"
        assert by_content["mode"] == "content"


def _check_apply_and_conflict() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        target = root / "app.py"
        _write_lf(target, "def main():\n    return 1\n")
        patch = (
            "*** Begin Patch\n"
            "*** Update File: app.py\n"
            "@@\n"
            " def main():\n"
            "-    return 1\n"
            "+    return 2\n"
            "*** End Patch\n"
        )
        ok = apply_patch(root, patch)
        assert ok["ok"] is True, ok
        assert ok["files_changed"] == ["app.py"]
        assert not ok["conflicts"]
        assert target.read_text(encoding="utf-8") == "def main():\n    return 2\n"

        bad = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Update File: app.py\n"
                "@@\n"
                " def main():\n"
                "-    return 99\n"
                "+    return 3\n"
                "*** End Patch\n"
            ),
        )
        assert bad["ok"] is False, bad
        assert bad["conflicts"], bad
        assert target.read_text(encoding="utf-8") == "def main():\n    return 2\n"


def _check_fingerprint_guard() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        target = root / "guard.txt"
        _write_lf(target, "one\n")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        mtime_ns = target.stat().st_mtime_ns
        # Stale expected hash must refuse write even when context would match.
        refused = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Update File: guard.txt\n"
                "@@\n"
                "-one\n"
                "+two\n"
                "*** End Patch\n"
            ),
            expected_sha256={"guard.txt": "0" * 64},
            expected_mtime_ns={"guard.txt": mtime_ns},
        )
        assert refused["ok"] is False, refused
        assert refused["conflicts"], refused
        assert target.read_text(encoding="utf-8") == "one\n"

        good = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Update File: guard.txt\n"
                "@@\n"
                "-one\n"
                "+two\n"
                "*** End Patch\n"
            ),
            expected_sha256={"guard.txt": digest},
            expected_mtime_ns={"guard.txt": mtime_ns},
        )
        assert good["ok"] is True, good
        assert target.read_text(encoding="utf-8") == "two\n"


def _check_absorb_wiring() -> None:
    assert "patch" not in strip_only_names()
    assert "apply_patch" in model_names()
    assert "patch" not in model_names()  # alias only — no dual schema
    assert resolve_action("apply_patch", "home") == "project.apply_patch"
    assert resolve_action("patch", "home") == "project.apply_patch"
    grant = PHASE4_ALLOWLIST.grant("project.apply_patch")
    assert grant is not None
    assert grant.parameters is not None
    props = grant.parameters.get("properties") or {}
    assert "patch_text" in props
    assert "patch" in props


def _check_atomic_no_tmp_junk() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        target = root / "clean.txt"
        _write_lf(target, "alpha\n")
        ok = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Update File: clean.txt\n"
                "@@\n"
                "-alpha\n"
                "+beta\n"
                "*** End Patch\n"
            ),
        )
        assert ok["ok"] is True, ok
        assert target.read_text(encoding="utf-8") == "beta\n"
        leftovers = [
            p
            for p in root.iterdir()
            if p.is_file() and (".tmp" in p.name.lower() or p.name.endswith(".iris-patch-tmp"))
        ]
        assert leftovers == [], leftovers


def _check_multifile_rollback() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        a = root / "a.txt"
        b = root / "b.txt"
        _write_lf(a, "A0\n")
        _write_lf(b, "B0\n")
        before_a = a.read_bytes()
        patch = (
            "*** Begin Patch\n"
            "*** Update File: a.txt\n"
            "@@\n"
            "-A0\n"
            "+A1\n"
            "*** Update File: b.txt\n"
            "@@\n"
            "-B0\n"
            "+B1\n"
            "*** End Patch\n"
        )
        real_replace = os.replace

        def flaky(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
            # Fail only the second target so rollback's own os.replace can succeed.
            if Path(dst).name == "b.txt":
                raise OSError("simulated mid-apply failure")
            real_replace(src, dst)

        os.replace = flaky  # type: ignore[assignment]
        try:
            bad = apply_patch(root, patch)
        finally:
            os.replace = real_replace  # type: ignore[assignment]
        assert bad["ok"] is False, bad
        assert a.read_bytes() == before_a, a.read_bytes()
        assert b.read_text(encoding="utf-8") == "B0\n"
        leftovers = [
            p
            for p in root.rglob("*")
            if p.is_file() and (".tmp" in p.name.lower() or p.name.endswith(".iris-patch-tmp"))
        ]
        assert leftovers == [], leftovers


def _check_crlf_preserved() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        target = root / "win.txt"
        _write_bytes(target, b"line1\r\nline2\r\n")
        ok = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Update File: win.txt\n"
                "@@\n"
                "-line2\n"
                "+line2b\n"
                "*** End Patch\n"
            ),
        )
        assert ok["ok"] is True, ok
        data = target.read_bytes()
        assert b"\r\n" in data, data
        assert b"\n" not in data.replace(b"\r\n", b""), data
        assert data == b"line1\r\nline2b\r\n", data


def _check_encoding_preserved() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        bom = root / "bom.txt"
        _write_bytes(bom, b"\xef\xbb\xbfhello\n")
        ok_bom = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Update File: bom.txt\n"
                "@@\n"
                "-hello\n"
                "+world\n"
                "*** End Patch\n"
            ),
        )
        assert ok_bom["ok"] is True, ok_bom
        assert bom.read_bytes().startswith(b"\xef\xbb\xbf"), bom.read_bytes()
        assert bom.read_bytes() == b"\xef\xbb\xbfworld\n", bom.read_bytes()

        latin = root / "latin.txt"
        _write_bytes(latin, "caf\u00e9\r\n".encode("latin-1"))
        ok_latin = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Update File: latin.txt\n"
                "@@\n"
                "-caf\u00e9\n"
                "+cafe\n"
                "*** End Patch\n"
            ),
        )
        assert ok_latin["ok"] is True, ok_latin
        assert latin.read_bytes() == b"cafe\r\n", latin.read_bytes()


def _check_delete_fingerprint_guard() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        target = root / "gone.txt"
        _write_lf(target, "stay\n")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        refused = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Delete File: gone.txt\n"
                "*** End Patch\n"
            ),
            expected_sha256={"gone.txt": "0" * 64},
        )
        assert refused["ok"] is False, refused
        assert target.is_file()
        assert target.read_text(encoding="utf-8") == "stay\n"

        good = apply_patch(
            root,
            (
                "*** Begin Patch\n"
                "*** Delete File: gone.txt\n"
                "*** End Patch\n"
            ),
            expected_sha256={"gone.txt": digest},
        )
        assert good["ok"] is True, good
        assert not target.exists()


def _check_buffer_sync_hook_stub() -> None:
    """Disk-side notify hook exists; Theia path is stub until real notify API is wired."""
    seen: list[tuple[str, list[str]]] = []

    class _Capture:
        def on_files_patched(self, root: str, paths: list[str]) -> None:
            seen.append((root, list(paths)))

    prev = get_patch_buffer_sync()
    set_patch_buffer_sync(_Capture())
    try:
        notify_files_patched("/tmp/proj", ["a.txt"])
        assert seen == [("/tmp/proj", ["a.txt"])], seen
        # apply_patch must call the hook only on success — and never claim Theia synced.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_lf(root / "x.txt", "1\n")
            seen.clear()
            out = apply_patch(
                root,
                (
                    "*** Begin Patch\n"
                    "*** Update File: x.txt\n"
                    "@@\n"
                    "-1\n"
                    "+2\n"
                    "*** End Patch\n"
                ),
            )
            assert out["ok"] is True, out
            assert seen and seen[0][1] == ["x.txt"], seen
            assert out.get("ide_refresh") in ("hook", "stub", "follow-up"), out
            note = str(out.get("note") or "").lower()
            assert "synced" not in note or "not" in note or "stub" in note or "follow" in note, out
    finally:
        set_patch_buffer_sync(prev)


def main() -> None:
    _check_read_range()
    _check_search_modes()
    _check_apply_and_conflict()
    _check_fingerprint_guard()
    _check_absorb_wiring()
    _check_atomic_no_tmp_junk()
    _check_multifile_rollback()
    _check_crlf_preserved()
    _check_encoding_preserved()
    _check_delete_fingerprint_guard()
    _check_buffer_sync_hook_stub()
    print("file_patch_engine ok")


if __name__ == "__main__":
    main()
