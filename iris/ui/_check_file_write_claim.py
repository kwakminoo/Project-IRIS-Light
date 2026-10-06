"""파일 쓰기 환각 방지 — 경로·펜스·완료 게이트·사진 파이프.

  .venv\\Scripts\\python.exe -m iris.ui._check_file_write_claim
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from iris.system.project_ops import code_fence_body_start, extract_first_code_block
from iris.ui.chat.at_path_refs import extract_at_path_refs, normalize_at_path, resolve_at_kind
from iris.ui.chat.file_write_claim import (
    CHAT_ONLY,
    apply_image_code_pipe,
    reveal_line,
    settle_completion_claim,
    verified_write_path,
)


class AtPathTests(unittest.TestCase):
    def test_normalize_drive_without_separator(self) -> None:
        if sys.platform != "win32":
            self.assertEqual(normalize_at_path("c:Users/kwakm/Desktop/foo"), "c:Users/kwakm/Desktop/foo")
            return
        self.assertEqual(
            normalize_at_path("c:Users/kwakm/Desktop/foo"),
            "c:\\Users\\kwakm\\Desktop\\foo",
        )
        self.assertEqual(normalize_at_path("c:\\Users\\kwakm\\Desktop\\foo"), "c:\\Users\\kwakm\\Desktop\\foo")
        self.assertEqual(normalize_at_path("c:/Users/kwakm/Desktop/foo"), "c:/Users/kwakm/Desktop/foo")
        self.assertEqual(normalize_at_path("mcp:foo"), "mcp:foo")

    def test_file_folder_missing_and_mcp(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iris-at-") as td:
            root = Path(td)
            folder = root / "pack"
            folder.mkdir()
            existing = root / "note.txt"
            existing.write_text("hi", encoding="utf-8")
            self.assertEqual(resolve_at_kind(str(existing))["kind"], "file")
            self.assertEqual(resolve_at_kind(str(folder))["kind"], "folder")
            parent = root / "search"
            parent.mkdir()
            (parent / "alpha notes").mkdir()
            missing = resolve_at_kind(str(parent / "alpha"), search_roots=[str(parent)])
            self.assertEqual(missing["kind"], "missing")
            self.assertLessEqual(len(missing["candidates"]), 5)
            self.assertTrue(any(Path(c).name == "alpha notes" for c in missing["candidates"]))
            self.assertEqual(resolve_at_kind("mcp:foo")["kind"], "missing")
            self.assertEqual(resolve_at_kind("mcp:foo")["candidates"], [])
            self.assertEqual(extract_at_path_refs("봐 @mcp:foo"), [])
            if sys.platform == "win32":
                full = str(existing.resolve())
                mangled = f"{full[0]}:{full[2:].lstrip(chr(92)).replace(chr(92), '/')}"
                hit = resolve_at_kind(mangled)
                self.assertEqual(hit["kind"], "file")
                self.assertEqual(Path(hit["path"]).resolve(), existing.resolve())


class CodeFenceTests(unittest.TestCase):
    def test_classic_and_glued_and_empty(self) -> None:
        classic = extract_first_code_block("```python\nprint(1)\n```")
        self.assertIsNotNone(classic)
        assert classic is not None
        self.assertEqual(classic["lang"], "python")
        self.assertEqual(classic["code"], "print(1)")
        glued = extract_first_code_block("```pythonimport cv2 as cv\nimg = 1\n```")
        self.assertIsNotNone(glued)
        assert glued is not None
        self.assertEqual(glued["lang"], "python")
        self.assertIn("import cv2 as cv", glued["code"])
        self.assertIn("img = 1", glued["code"])
        self.assertIsNone(extract_first_code_block("print(1)"))
        self.assertIsNone(extract_first_code_block("```python\n\n```"))
        self.assertIsNone(extract_first_code_block("``````"))
        opened = code_fence_body_start("```pythonimport cv2 as cv")
        self.assertIsNotNone(opened)
        assert opened is not None
        self.assertEqual(opened[0], "python")
        self.assertIsNone(code_fence_body_start("```python"))


class CompletionGateTests(unittest.TestCase):
    def test_ok_file_present_includes_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iris-gate-") as td:
            path = Path(td) / "kept.py"
            path.write_text("print(1)\n", encoding="utf-8")
            result = {"ok": True, "result": {"path": str(path)}}
            line = reveal_line(verified_write_path(result))
            self.assertIn(str(path.resolve()), line)
            said = "처리 완료"
            gate = settle_completion_claim(said, verified_path=str(path))
            self.assertEqual(gate.display, said)
            self.assertFalse(gate.suppress_followup_write)

    def test_ok_without_file_is_not_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iris-gate-") as td:
            ghost = str(Path(td) / "missing.py")
            result = {"ok": True, "result": {"path": ghost}}
            line = reveal_line(verified_write_path(result))
            self.assertEqual(line, CHAT_ONLY)
            self.assertNotIn("열었습니다", line)
            self.assertNotIn("처리 완료", line)

    def test_claim_without_tool_is_not_success(self) -> None:
        said = "interpolation_test.py 를 생성하겠습니다. 처리 완료"
        gate = settle_completion_claim(said, verified_path="", try_write=None)
        self.assertEqual(gate.display, said)
        self.assertNotIn("채팅에만 있고", gate.display)

    def test_claim_with_fence_writes_once(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iris-gate-") as td:
            root = Path(td)
            calls: list[str] = []

            def try_write(code: str, lang: str) -> dict:
                calls.append(lang)
                path = root / "from_fence.py"
                path.write_text(code, encoding="utf-8")
                return {"ok": True, "result": {"path": str(path)}}

            said = "작성했습니다\n```python\nprint(1)\n```"
            gate = settle_completion_claim(said, verified_path="", try_write=try_write)
            self.assertEqual(calls, [])
            self.assertEqual(gate.display, said)
            self.assertFalse((root / "from_fence.py").exists())


class ImagePipeTests(unittest.TestCase):
    def test_writes_open_file_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iris-pipe-") as td:
            root = Path(td)
            target = root / "kept.py"
            target.write_text("old\n", encoding="utf-8")
            shot = root / "shot.png"
            shot.write_bytes(b"png")

            def write_file(rel: str, content: str) -> dict:
                path = root / rel
                path.write_text(content, encoding="utf-8")
                return {"ok": True, "result": {"path": str(path)}}

            out = apply_image_code_pipe(
                "이 사진속 코드를 이 스크립트 안에 작성해줘",
                [str(shot)],
                project_root=str(root),
                list_editors=lambda: [{"path": str(target)}],
                extract=lambda _image: "print(1)",
                write_file=write_file,
            )
            self.assertTrue(out["handled"])
            self.assertEqual(out["write_count"], 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "print(1)")
            self.assertIn(str(target.resolve()), out["message"])
            self.assertFalse((root / "interpolation_test.py").exists())
            self.assertNotIn("interpolation_test.py", out["message"])

    def test_missing_at_and_no_editor_do_not_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="iris-pipe-") as td:
            root = Path(td)
            shot = root / "shot.png"
            shot.write_bytes(b"png")
            parent = root / "search"
            parent.mkdir()
            (parent / "alpha notes").mkdir()
            writes = {"n": 0}

            def write_file(rel: str, content: str) -> dict:
                writes["n"] += 1
                return {"ok": True, "result": {"path": str(root / rel)}}

            missing = apply_image_code_pipe(
                "@c:Users/no/such/alpha 코드를 작성해줘",
                [str(shot)],
                project_root=str(root),
                search_roots=[str(parent)],
                list_editors=lambda: [{"path": str(root / "kept.py")}],
                extract=lambda _image: "print(1)",
                write_file=write_file,
            )
            self.assertFalse(missing["handled"])
            self.assertEqual(missing["write_count"], 0)
            self.assertEqual(writes["n"], 0)
            self.assertNotIn("경로가 없습니다", missing["message"])

            opened: list[str] = []
            folder = root / "pack"
            folder.mkdir()
            no_editor = apply_image_code_pipe(
                f"@{folder} 이 스크립트에 넣어줘",
                [str(shot)],
                project_root=str(root),
                list_editors=lambda: [],
                extract=lambda _image: "print(1)",
                write_file=write_file,
                open_folder=opened.append,
            )
            self.assertEqual(no_editor["write_count"], 0)
            self.assertEqual(writes["n"], 0)
            self.assertTrue(opened)
            self.assertFalse(no_editor["handled"])
            self.assertNotIn("파일명", no_editor["message"])

            many = apply_image_code_pipe(
                "코드를 작성해줘",
                [str(shot)],
                project_root=str(root),
                list_editors=lambda: [{"path": str(root / "a.py")}, {"path": str(root / "b.py")}],
                extract=lambda _image: "print(1)",
                write_file=write_file,
            )
            self.assertEqual(many["write_count"], 0)
            self.assertEqual(writes["n"], 0)
            self.assertFalse(many["handled"])
            self.assertNotIn("여러 개", many["message"])

            plain = apply_image_code_pipe(
                "안녕",
                [],
                project_root=str(root),
                list_editors=lambda: [{"path": str(root / "kept.py")}],
                extract=lambda _image: "print(1)",
                write_file=write_file,
            )
            self.assertFalse(plain["handled"])
            self.assertEqual(plain["write_count"], 0)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
