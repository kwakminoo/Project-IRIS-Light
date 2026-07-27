"""프로젝트 폴더 찾기·스캐폴드·파일 쓰기 (Iris Control용).

ponytail: difflib 유사도 + 알려진 부모 디렉터리만 스캔.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path


def default_project_parents() -> list[Path]:
    home = Path.home()
    cands = [
        home / "Desktop" / "Cusor-Project",
        home / "Desktop" / "Cursor-Project",
        home / "Desktop" / "Projects",
        home / "Documents" / "Projects",
        home / "Desktop",
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for p in cands:
        try:
            r = p.resolve()
        except OSError:
            continue
        if not r.is_dir():
            continue
        key = str(r).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def resolve_project_parents(custom: list[str] | None = None) -> list[Path]:
    """설정 부모 목록이 있으면 그것만, 없으면 기본 후보."""
    if custom:
        out: list[Path] = []
        seen: set[str] = set()
        for raw in custom:
            s = str(raw or "").strip()
            if not s:
                continue
            try:
                r = Path(s).expanduser().resolve()
            except OSError:
                continue
            if not r.is_dir():
                continue
            key = str(r).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        if out:
            return out
    return default_project_parents()


def _norm_name(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("_", "-").replace(" ", "-")
    s = re.sub(r"-+", "-", s)
    return s


def find_similar_projects(
    query: str,
    *,
    parents: list[Path] | None = None,
    limit: int = 8,
    min_score: float = 0.35,
) -> list[dict]:
    """query에 가장 비슷한 하위 폴더 목록 (score 내림차순)."""
    q = _norm_name(query)
    if not q:
        return []
    parents = parents or default_project_parents()
    scored: list[tuple[float, Path]] = []
    for parent in parents:
        try:
            kids = list(parent.iterdir())
        except OSError:
            continue
        for child in kids:
            if not child.is_dir() or child.name.startswith("."):
                continue
            name = child.name
            nn = _norm_name(name)
            score = SequenceMatcher(None, q, nn).ratio()
            # 부분 포함 보너스
            if q in nn or nn in q:
                score = max(score, 0.72)
            # 토큰 겹침
            qt = set(q.split("-"))
            nt = set(nn.split("-"))
            if qt and nt:
                overlap = len(qt & nt) / max(len(qt), 1)
                score = max(score, 0.4 + 0.5 * overlap)
            if score >= min_score:
                scored.append((score, child))
    scored.sort(key=lambda x: (-x[0], x[1].name.lower()))
    # path 중복 제거
    seen: set[str] = set()
    out: list[dict] = []
    for score, path in scored:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "score": round(float(score), 4),
                "parent": str(path.parent),
            }
        )
        if len(out) >= limit:
            break
    return out


def pick_similar_project(
    query: str,
    *,
    parents: list[Path] | None = None,
    force: bool = False,
    min_clear_score: float = 0.55,
    min_margin: float = 0.08,
    **kwargs,
) -> tuple[dict | None, list[dict], str]:
    """(best, matches, reason). reason: ok | none | low_score | ambiguous.

    force=True면 1등(있을 때)을 그대로 고른다.
    """
    hits = find_similar_projects(query, parents=parents, **kwargs)
    if not hits:
        return None, [], "none"
    if force:
        return hits[0], hits, "ok"
    top = hits[0]
    if float(top["score"]) < min_clear_score:
        return None, hits, "low_score"
    if len(hits) > 1 and (float(top["score"]) - float(hits[1]["score"])) < min_margin:
        return None, hits, "ambiguous"
    return top, hits, "ok"


def best_similar_project(query: str, **kwargs) -> dict | None:
    best, _hits, reason = pick_similar_project(query, force=True, **kwargs)
    return best if reason == "ok" else None


_GUGUDAN_PY = '''\
"""숫자를 입력받아 해당 단 구구단을 출력합니다."""


def print_gugudan(n: int) -> None:
    print(f"=== {n}단 ===")
    for i in range(1, 10):
        print(f"{n} x {i} = {n * i}")


def main() -> None:
    raw = input("몇 단을 출력할까요? (정수): ").strip()
    n = int(raw)
    print_gugudan(n)


if __name__ == "__main__":
    main()
'''


def create_scaffold(
    parent: str | Path,
    name: str,
    *,
    template: str = "empty",
) -> dict:
    """부모 아래 name 폴더 생성 + 템플릿 파일.

    template: empty | gugudan | python-hello
    """
    parent_p = Path(parent).expanduser().resolve()
    if not parent_p.is_dir():
        raise FileNotFoundError(f"parent not a directory: {parent_p}")
    safe = re.sub(r'[<>:"/\\|?*]', "-", (name or "").strip()) or "iris-project"
    root = (parent_p / safe).resolve()
    if parent_p not in root.parents and root != parent_p:
        # 안전: parent 밖으로 못 나가게
        if not str(root).startswith(str(parent_p)):
            raise ValueError("invalid project path")
    root.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    readme = root / "README.md"
    if not readme.is_file():
        readme.write_text(f"# {safe}\n\nCreated by Iris Light.\n", encoding="utf-8")
        files.append("README.md")
    tmpl = (template or "empty").strip().lower()
    if tmpl == "gugudan":
        main_py = root / "gugudan.py"
        main_py.write_text(_GUGUDAN_PY, encoding="utf-8")
        files.append("gugudan.py")
    elif tmpl in ("python-hello", "hello"):
        main_py = root / "main.py"
        if not main_py.is_file():
            main_py.write_text("print('hello iris')\n", encoding="utf-8")
            files.append("main.py")
    return {"path": str(root), "name": safe, "files": files, "template": tmpl}


def write_project_file(project_root: str | Path, rel_path: str, content: str) -> dict:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("invalid rel_path")
    path = (root / rel).resolve()
    if root not in path.parents and path != root:
        raise ValueError("path escapes project_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": str(path), "rel_path": rel, "bytes": len(content.encode("utf-8"))}


if __name__ == "__main__":
    hits = find_similar_projects("ai guitar tab")
    assert hits, "expected AI-Guitar-Tab-main nearby"
    assert "guitar" in hits[0]["name"].lower()
    best, amb, reason = pick_similar_project("ai guitar tab")
    assert reason == "ok" and best is not None
    parents = resolve_project_parents([])
    assert parents
    print("project_ops ok", hits[0]["name"], hits[0]["score"], reason)
