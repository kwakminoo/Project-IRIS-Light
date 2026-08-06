"""Iris 소스코드(iris/*.py)를 훑어 모듈 docstring/정의/import 관계를 뽑아주는 가벼운 인덱서.

위키 그래프(wiki_graph_view.py)가 직접 참조하지는 않는다 — scripts/generate_code_docs.py가
이 정보를 obsidian-vault 아래 실제 .md 노트로 구워내면, 그 노트들이 기존 위키 파이프라인을 타고
왼쪽 문서 패널과 구체 그래프 양쪽에 자연스럽게 나타난다.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

IRIS_ROOT = Path(__file__).resolve().parent.parent  # .../iris
_SKIP_DIR_NAMES = {"__pycache__"}


@dataclass(frozen=True)
class CodeFile:
    rel_path: str  # 예: "ui/knowledge/wiki_graph_view.py"
    title: str  # 예: "wiki_graph_view"
    folder: str  # 최상위 패키지 폴더 (예: "ui") — 문서 묶음 단위
    module: str  # 점(.) 표기 모듈 경로 (예: "iris.ui.knowledge.wiki_graph_view")
    doc: str  # 모듈 docstring 첫 줄 (없으면 "")
    symbols: list[str] = field(default_factory=list)  # 최상위 class/def 이름
    imports: list[str] = field(default_factory=list)  # 이 파일이 import하는 iris 내부 모듈들

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.folder.lower(), self.title.lower())


class IrisCodeIndex:
    """iris/ 패키지 안의 .py 파일과 iris 내부 import 관계를 스캔한다."""

    def list_files(self) -> list[CodeFile]:
        files: list[CodeFile] = []
        if not IRIS_ROOT.is_dir():
            return files
        for path in sorted(IRIS_ROOT.rglob("*.py")):
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            rel = path.relative_to(IRIS_ROOT)
            folder = rel.parts[0] if len(rel.parts) > 1 else "root"
            if rel.stem == "__init__":
                # 패키지 자신을 가리키는 실제 import 경로("iris.ui")에 맞춘다.
                title = rel.parent.name or "iris"
                module = "iris." + ".".join(rel.parent.parts) if rel.parent.parts else "iris"
            else:
                title = rel.stem
                module = "iris." + ".".join(rel.with_suffix("").parts)
            doc, symbols, imports = self._parse(path)
            files.append(
                CodeFile(
                    rel_path=rel.as_posix(),
                    title=title,
                    folder=folder,
                    module=module,
                    doc=doc,
                    symbols=symbols,
                    imports=imports,
                )
            )
        return files

    def _parse(self, path: Path) -> tuple[str, list[str], list[str]]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:  # noqa: BLE001
            return "", [], []

        doc = (ast.get_docstring(tree) or "").strip().splitlines()[0] if ast.get_docstring(tree) else ""

        symbols = [
            ("class " if isinstance(node, ast.ClassDef) else "def ") + node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("iris"):
                imports.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("iris"):
                        imports.append(alias.name)
        return doc, symbols, imports
