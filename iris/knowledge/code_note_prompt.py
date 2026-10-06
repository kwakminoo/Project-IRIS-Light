"""아이리스 구조 노트 발췌. 사용자 위키 테이블(wiki_notes)과 나누어 둔다.

노트 첫 줄이 소스와 다르면 그 문장을 근거로 쓰지 않고 모듈 docstring 전체를 넣는다.
ponytail: 구조 질문마다 코드/·Iris Light/ md를 한 번 훑는다. 노트가 수천이면 FTS가 다음 단계.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from iris.knowledge.history_index import like_terms, like_variants
from iris.knowledge.obsidian_vault import DEFAULT_VAULT_ROOT

_FOLDERS = ("코드", "Iris Light")
_EXCERPT = 800
_TOTAL = 2400
_TOP_K = 3
_PY_IN_NOTE = re.compile(r"`(iris/[^`\s]+?\.py)`")
_STOP = {"어떻게", "무엇", "이거", "여기", "되지", "있어", "하는", "해서", "그게"}

_HEADER = (
    "# 아이리스 소스 노트\n\n"
    "아래는 아이리스 구조 노트의 발췌다. 사용자 위키 노트와 다른 출처다.\n"
)

_PROJECT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CodeHit:
    rel_path: str
    title: str
    excerpt: str
    score: int


def _terms(query: str) -> list[tuple[str, int]]:
    raw = [term for term in like_terms(query) if term not in _STOP]
    if not raw:
        raw = like_terms(query)
    weighted: list[tuple[str, int]] = []
    seen: set[str] = set()
    for term in raw:
        if term not in seen:
            seen.add(term)
            weighted.append((term, 2))
        for variant in like_variants(term):
            if variant not in seen and variant not in _STOP:
                seen.add(variant)
                weighted.append((variant, 1))
    return weighted


def _score(text: str, weighted: list[tuple[str, int]]) -> int:
    folded = (text or "").casefold()
    return sum(weight for term, weight in weighted if term.casefold() in folded)


def _module_doc(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ""
    return (ast.get_docstring(tree) or "").strip()


def _project_py(project: Path, rel: str) -> Path | None:
    path = (project / rel).resolve()
    root = project.resolve()
    if path != root and root not in path.parents:
        return None
    if path.suffix != ".py" or not path.is_file():
        return None
    return path


def body_for_prompt(note: Path, text: str, *, project: Path) -> str:
    """노트에 없는 계약은 소스 docstring으로 바꾼다. 첫 줄만 있는 70:30은 버린다."""
    raw = (text or "").strip()
    match = _PY_IN_NOTE.search(raw)
    if match is None:
        return raw
    src = _project_py(project, match.group(1))
    if src is None:
        return raw
    doc = _module_doc(src)
    if not doc:
        return raw
    try:
        newer = src.stat().st_mtime_ns > note.stat().st_mtime_ns
    except OSError:
        newer = False
    if newer or doc not in raw:
        return f"`{match.group(1)}`\n\n{doc}"
    return raw


def search_code_notes(
    vault: Path,
    query: str,
    *,
    project: Path | None = None,
    limit: int = _TOP_K,
) -> list[CodeHit]:
    weighted = _terms(query)
    if not weighted:
        return []
    root = Path(vault)
    project_root = Path(project) if project is not None else _PROJECT
    scored: list[tuple[int, str, Path, str]] = []
    for folder in _FOLDERS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            if path.name.startswith("."):
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = path.relative_to(root).as_posix()
            score = _score(f"{rel}\n{body[:4000]}", weighted)
            if score <= 0:
                continue
            scored.append((score, rel, path, body))
    scored.sort(key=lambda item: (-item[0], item[1]))
    hits: list[CodeHit] = []
    for score, rel, path, body in scored[: int(limit)]:
        fresh = body_for_prompt(path, body, project=project_root).strip()
        if len(fresh) > _EXCERPT:
            fresh = fresh[:_EXCERPT]
        if not fresh:
            continue
        hits.append(CodeHit(rel_path=rel, title=path.stem, excerpt=fresh, score=score))
    return hits


def empty_code_block(query: str) -> str:
    q = " ".join((query or "").split())[:80] or "(빈 질문)"
    return (
        "# 아이리스 소스 노트\n\n"
        f"「{q}」로 코드 노트를 찾았고 0건이다.\n"
    )


def format_code_prompt(hits: list[CodeHit]) -> str:
    if not hits:
        return ""
    blocks = [_HEADER]
    used = 0
    for hit in hits:
        piece = hit.excerpt.strip()
        room = _TOTAL - used
        if room <= 0:
            break
        if len(piece) > room:
            piece = piece[:room]
        if not piece:
            continue
        blocks.append(f"### {hit.title} (docs/{hit.rel_path})\n{piece}\n")
        used += len(piece)
    if len(blocks) == 1:
        return ""
    return "\n".join(blocks).strip() + "\n"


def code_prompt_for_query(
    vault: Path,
    query: str,
    *,
    on_empty: bool = False,
    project: Path | None = None,
    limit: int = _TOP_K,
) -> str:
    try:
        hits = search_code_notes(vault, query, project=project, limit=limit)
    except OSError:
        hits = []
    block = format_code_prompt(hits)
    if block.strip():
        return block
    if on_empty:
        return empty_code_block(query)
    return ""


def _check() -> None:
    import tempfile

    from iris.knowledge.wiki_note_index import format_note_prompt

    assert format_code_prompt([]) == ""
    assert "저장된 자료" not in _HEADER
    assert "아이리스 소스 노트" not in format_note_prompt([])
    empty = code_prompt_for_query(Path("."), "없는모듈xyz", on_empty=True)
    assert "0건" in empty and "없다고만" not in empty
    assert code_prompt_for_query(Path("."), "없는모듈xyz", on_empty=False) == ""

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault = root / "vault"
        note = vault / "코드" / "system" / "ide_tiler.md"
        src = root / "iris" / "system" / "ide_tiler.py"
        note.parent.mkdir(parents=True)
        src.parent.mkdir(parents=True)
        src.write_text(
            '"""IDE / Iris 창을 주 모니터 work area 기준 80:20 타일 배치.\n\n'
            "계약: setGeometry only.\n"
            '"""\n',
            encoding="utf-8",
        )
        note.write_text(
            "# ide_tiler\n\n`iris/system/ide_tiler.py`\n\n"
            "IDE / Iris 창을 주 모니터 work area 기준 70:30 타일 배치.\n",
            encoding="utf-8",
        )
        block = code_prompt_for_query(vault, "타일 비율이 어떻게 되지", on_empty=True, project=root)
        assert "80:20" in block and "70:30" not in block
        assert "아이리스 소스 노트" in block and "저장된 자료" not in block
        assert "docs/코드/system/ide_tiler.md" in block

    real = DEFAULT_VAULT_ROOT / "코드" / "system" / "ide_tiler.md"
    if real.is_file():
        live = code_prompt_for_query(DEFAULT_VAULT_ROOT, "타일 비율", on_empty=True)
        assert "80:20" in live and "70:30" not in live, live[:400]
    print("code_note_prompt ok")


if __name__ == "__main__":
    _check()
