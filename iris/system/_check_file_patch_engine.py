"""U06 — File & Patch Engine.

Fails when:
- read_text_range lacks line range / truncation flag
- search_files does not distinguish name vs content mode
- apply_patch cannot apply a unified-diff / Hermes-style patch
- missing expected context does not conflict
- apply_patch overwrites when disk hash/mtime fingerprint drifted

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_file_patch_engine
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from iris.infrastructure.absorbed_tool_aliases import (
    model_names,
    resolve_action,
    strip_only_names,
)
from iris.infrastructure.speak_capability import PHASE4_ALLOWLIST
from iris.system.file_patch import apply_patch, read_text_range, search_files


def _write_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


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


def main() -> None:
    _check_read_range()
    _check_search_modes()
    _check_apply_and_conflict()
    _check_fingerprint_guard()
    _check_absorb_wiring()
    print("file_patch_engine ok")


if __name__ == "__main__":
    main()
