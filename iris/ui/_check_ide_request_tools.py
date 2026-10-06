"""PDF 도구·설치 범위·마켓플레이스 VSIX·IDE 위키 기록 자검.

  .venv\\Scripts\\python.exe -m iris.ui._check_ide_request_tools
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

from iris.knowledge.ide_project_log import note_opened, note_update
from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.pdf_job import compose_pdf_text, resolve_pdf_dest
from iris.system.extension_scope import choose_extension_scope
from iris.system.github_extension_install import _write_server
from iris.system.project_marketplace import install_extension, pin_extension, search_extensions
from iris.ui.chat.file_write_claim import settle_completion_claim


def check_pdf() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-pdf-job-") as td:
        root = Path(td)
        src = root / "main.py"
        src.write_text("print(1)\napi_key=sk-" + ("a" * 24) + "\n", encoding="utf-8")
        body = compose_pdf_text("제출 요약", [str(src)], str(root))
        assert "제출 요약" in body
        assert "print(1)" in body
        assert "sk-" not in body
        assert "[redacted]" in body
        dest = resolve_pdf_dest("out/note.pdf", str(root))
        assert dest == (root / "out" / "note.pdf").resolve() or dest == root / "out" / "note.pdf"
        assert resolve_pdf_dest("", str(root)) == root / "iris-note.pdf"
        assert resolve_pdf_dest("", "") == Path.home() / "Documents" / "IRIS" / "iris-note.pdf"

    said = "PDF로 저장했습니다."
    missing = settle_completion_claim(said, verified_path="")
    assert missing.display == said
    with tempfile.TemporaryDirectory(prefix="iris-pdf-gate-") as td:
        path = Path(td) / "out.pdf"
        path.write_bytes(b"%PDF-1.4")
        kept = "저장했습니다"
        gate = settle_completion_claim(kept, verified_path=str(path))
        assert gate.display == kept
        assert "PDF로 저장했습니다" not in gate.display


def check_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-scope-") as td:
        got, err = choose_extension_scope("ide_companion", td, "")
        assert got == "project" and err == "", (got, err)
        got, err = choose_extension_scope("ide_companion", td, "iris")
        assert got == "" and "기본 화면" in err
        got, err = choose_extension_scope("assistant", td, "")
        assert got == "iris" and err == ""
        got, err = choose_extension_scope("assistant", td, "project")
        assert got == "" and "아이리스 IDE" in err
        home = Path(td) / ".iris"
        home.mkdir()
        (home / "PROJECT").write_text(td, encoding="utf-8")
        _write_server(home, "demo", {"command": "node", "args": ["a.js"], "env": {}})
        assert (home / "mcp.json").is_file()
        assert not (home / "config.yaml").exists()


def check_market_and_wiki() -> None:
    rows = search_extensions(
        "python",
        fetch=lambda _url: {
            "extensions": [
                {"namespace": "ms-python", "name": "python", "version": "1", "displayName": "Python"},
                {"namespace": "bad id", "name": "nope"},
            ]
        },
    )
    assert rows == [{"id": "ms-python.python", "version": "1", "display_name": "Python"}]
    try:
        search_extensions("  ")
        raise AssertionError("empty query")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory(prefix="iris-vsx-") as td:
        pinned = pin_extension(td, "ms-python.python")
        assert "ms-python.python" in Path(pinned["recommendations"]).read_text(encoding="utf-8")
        assert "ms-python.python" in Path(pinned["record"]).read_text(encoding="utf-8")
        docs = Path(td) / "docs"
        user = Path(td) / "wiki"
        wiki = IrisWiki(docs, user)
        rel = note_opened(wiki, td)
        assert rel.startswith("아이리스 IDE/")
        text = (user / rel).read_text(encoding="utf-8")
        assert "프로젝트를 열었습니다" in text
        note_update(wiki, td, plan="다음 주에 제출", decision="PDF는 도구로", issue="탭 클릭이 끊김")
        text = (user / rel).read_text(encoding="utf-8")
        assert "다음 주에 제출" in text
        assert "PDF는 도구로" in text
        assert "탭 클릭이 끊김" in text
        note_update(wiki, td, issue="api_key=sk-" + ("b" * 24))
        text = (user / rel).read_text(encoding="utf-8")
        assert "sk-" not in text


def _vsix(payload: dict, extra: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("extension.vsixmanifest", "<PackageManifest/>")
        zf.writestr("extension/package.json", json.dumps(payload))
        for name, text in (extra or {}).items():
            zf.writestr(name, text)
    return buf.getvalue()


def check_vsix_deploy() -> None:
    good = {
        "name": "python",
        "publisher": "ms-python",
        "version": "1.2.3",
        "engines": {"vscode": "^1.60.0"},
    }
    blob = _vsix(good)
    meta = {
        "version": "1.2.3",
        "files": {"download": "https://open-vsx.org/api/ms-python/python/1.2.3/file/x.vsix"},
    }

    def fetch(url: str) -> dict:
        assert url.endswith("/ms-python/python")
        return meta

    with tempfile.TemporaryDirectory(prefix="iris-vsix-") as td:
        root = Path(td) / "proj"
        deploy = Path(td) / "deployedPlugins"
        root.mkdir()
        got = install_extension(str(root), "ms-python.python", str(deploy), fetch=fetch, download=lambda _u: blob)
        package = Path(got["package"])
        assert package.is_file()
        assert json.loads(package.read_text(encoding="utf-8"))["engines"]["vscode"]
        record = json.loads(Path(got["record"]).read_text(encoding="utf-8"))
        assert record[0]["version"] == "1.2.3"
        assert record[0]["deployed"] == got["deployed"]
        slipped = _vsix(good, {"../outside.txt": "nope"})
        try:
            install_extension(
                str(root),
                "ms-python.python",
                str(deploy),
                fetch=fetch,
                download=lambda _u: slipped,
            )
        except ValueError:
            pass
        assert not (Path(td) / "outside.txt").exists()
        bare = _vsix({"name": "python", "version": "1.2.3"})
        try:
            install_extension(str(root), "ms-python.python", str(deploy), fetch=fetch, download=lambda _u: bare)
            raise AssertionError("missing engines")
        except ValueError as exc:
            assert "engines.vscode" in str(exc)
        assert not (deploy / "ms-python.python").exists()


def main() -> None:
    check_pdf()
    check_scope()
    check_market_and_wiki()
    check_vsix_deploy()
    print("ide request tools ok")


if __name__ == "__main__":
    main()
