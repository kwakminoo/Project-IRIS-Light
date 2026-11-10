"""프로젝트 폴더 찾기·스캐폴드·파일 쓰기 (Iris Control용).

ponytail: difflib 유사도 + 알려진 부모 디렉터리만 스캔.
"""

from __future__ import annotations

import re
import shutil
import sys
from collections.abc import Callable
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
    # Iris Light: Project-IRIS-Light-main 을 짧은 "iris light" 쿼리에서 최우선
    if "iris" in q and "light" in q:
        boosted: list[tuple[float, Path]] = []
        for score, child in scored:
            nn = _norm_name(child.name)
            if nn.endswith("-main") and "iris" in nn and "light" in nn:
                score = max(score, 0.98)
            elif nn in {"iris", "project-iris"} or (
                "iris" in nn and "light" not in nn and "hud" not in nn
            ):
                # 구 Project---IRIS / IRIS 폴더는 Light와 혼동 금지
                score = min(score, 0.34)
            boosted.append((score, child))
        scored = boosted
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


def workspace_rel_for_open(workspace_root: str | Path, path: str) -> str:
    """상대 경로는 워크스페이스 기준. cwd로 풀지 않는다. 밖과 .. 는 거절."""
    import os

    raw_text = str(path or "").strip()
    if not raw_text or ".." in Path(raw_text.replace("\\", "/")).parts:
        raise ValueError("path escapes workspace")
    root = Path(workspace_root).expanduser().resolve()
    raw = Path(raw_text)
    target = raw if raw.is_absolute() else (root / raw)
    try:
        target = target.resolve()
    except OSError as exc:
        raise ValueError("path escapes workspace") from exc
    root_key = os.path.normcase(str(root))
    target_key = os.path.normcase(str(target))
    if target_key != root_key and not target_key.startswith(root_key + os.sep):
        raise ValueError("path escapes workspace")
    rel = Path(os.path.relpath(str(target), str(root)))
    if not rel.parts or rel.parts[0] == "..":
        raise ValueError("path escapes workspace")
    return rel.as_posix()


def resolve_under_root(project_root: str | Path, rel_path: str) -> tuple[Path, Path, str]:
    """(root, abs_path, rel). path escape 검증."""
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("invalid rel_path")
    path = (root / rel).resolve()
    if root not in path.parents and path != root:
        raise ValueError("path escapes project_root")
    return root, path, rel


def utf8_content_matches(path: Path, content: str) -> bool:
    try:
        return path.read_text(encoding="utf-8") == content
    except OSError:
        return False


def write_project_file(project_root: str | Path, rel_path: str, content: str) -> dict:
    _root, path, rel = resolve_under_root(project_root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = str(content)
    path.write_text(text, encoding="utf-8")
    match = utf8_content_matches(path, text)
    out: dict = {
        "path": str(path),
        "rel_path": rel,
        "bytes": len(text.encode("utf-8")),
        "content_match": match,
    }
    if not match:
        out["error"] = "UTF-8 content readback mismatch"
    return out


def read_project_file(
    project_root: str | Path, rel_path: str, *, max_bytes: int = 1_048_576
) -> dict:
    """Disk UTF-8 dual of write_project_file. Guards fail before inventing content."""
    _root, path, rel = resolve_under_root(project_root, rel_path)
    if path.is_dir():
        raise IsADirectoryError(f"{path} is a directory")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file too large (max {max_bytes} bytes)")
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise ValueError("not UTF-8 text")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8 text") from exc
    return {
        "path": str(path),
        "rel_path": rel,
        "bytes": len(raw),
        "encoding": "utf-8",
        "content": content,
    }


def is_run_request(text: str) -> bool:
    s = (text or "").lower()
    return any(w in s for w in ("실행", "출력", "돌려", "run", "execute", "print"))


_FENCE_LANGS = tuple(
    sorted(
        {
            "python", "py", "javascript", "js", "typescript", "ts", "tsx", "jsx",
            "bash", "sh", "shell", "json", "html", "css", "cpp", "c", "java",
            "go", "rust", "rs", "ruby", "rb", "php", "sql", "markdown", "md",
            "yaml", "yml", "xml", "text", "plaintext", "kotlin", "swift", "lua",
            "csharp", "cs",
        },
        key=len,
        reverse=True,
    )
)


def _fence_header(line: str) -> tuple[str, str] | None:
    """펜스 첫 줄 → (lang, 같은 줄에 붙은 코드).

    None 이면 언어 태그가 아직 덜 옴(다음 청크를 기다린다).
    인라인 코드가 비면 본문은 다음 줄부터다.
    """
    raw = line or ""
    s = raw.strip()
    if not s:
        return "", ""
    low = s.lower()
    if any(lang.startswith(low) and lang != low for lang in _FENCE_LANGS):
        return None
    for lang in _FENCE_LANGS:
        if (
            low == lang
            or low.startswith(lang + " ")
            or low.startswith(lang + "\t")
            or low.startswith(lang + ":")
        ):
            return lang, ""
        if not low.startswith(lang):
            continue
        if any(other.startswith(low) and len(other) > len(lang) for other in _FENCE_LANGS):
            continue
        rest = s[len(lang) :]
        if rest[:1].isalnum() or rest[:1] == "_":
            return lang, rest
    token = s.split()[0]
    if re.fullmatch(r"[A-Za-z0-9_+#.\-]{1,32}", token) and (
        " " in s or ":" in s or token == s
    ):
        return token.lower(), ""
    return "", s


def code_fence_body_start(raw: str) -> tuple[str, int] | None:
    """첫 펜스가 열렸으면 (lang, 코드 시작 인덱스). 없거나 헤더가 덜 오면 None."""
    text = raw or ""
    idx = text.find("```")
    if idx < 0:
        return None
    after = idx + 3
    rest = text[after:]
    nl = rest.find("\n")
    close = rest.find("```")
    if nl < 0 or (close >= 0 and close < nl):
        chunk = rest[:close] if close >= 0 else rest
        parts = _fence_header(chunk)
        if parts is None:
            return None
        lang, inline = parts
        if not inline.strip():
            return None
        lead = len(chunk) - len(chunk.lstrip())
        return lang, after + lead + (len(chunk.strip()) - len(inline))
    line = rest[:nl]
    parts = _fence_header(line)
    if parts is None:
        return None
    lang, inline = parts
    if inline:
        lead = len(line) - len(line.lstrip())
        return lang, after + lead + (len(line.strip()) - len(inline))
    return lang, after + nl + 1


def extract_first_code_block(text: str) -> dict | None:
    opened = code_fence_body_start(text or "")
    if opened is None:
        return None
    lang, start = opened
    tail = (text or "")[start:]
    end = tail.find("```")
    if end < 0:
        return None
    code = tail[:end].strip("\n")
    if not code.strip():
        return None
    return {"lang": lang, "code": code}


_LANG_SUFFIX = {
    "python": ".py",
    "py": ".py",
    "javascript": ".js",
    "js": ".js",
    "typescript": ".ts",
    "ts": ".ts",
}


def _lang_suffix(lang: str) -> str:
    return _LANG_SUFFIX.get((lang or "").lower(), ".py")


def default_generated_rel_path(prompt: str, lang: str) -> str:
    """펜스 폴백용 고정 이름. 사용자 문장에서 파일명을 읽지 않는다."""
    del prompt
    return "iris_generated" + _lang_suffix(lang)


def iris_repo_root() -> Path:
    """이 패키지가 속한 Iris 워크스페이스 루트 (iris/ 의 부모)."""
    return Path(__file__).resolve().parents[2]


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def dangerous_delete_reason(target: Path) -> str | None:
    """삭제 거절 사유. None 이면 경로 자체는 허용 후보."""
    try:
        t = target.expanduser().resolve()
    except OSError as exc:
        return f"cannot resolve path: {exc}"
    if t.parent == t:
        return "refusing to delete drive root"
    home = Path.home().resolve()
    if t == home:
        return "refusing to delete home directory"
    if t != home and _path_contains(t, home):
        return "refusing to delete a home ancestor"
    iris_data = (Path.home() / ".iris-light").resolve()
    if t == iris_data or _path_contains(t, iris_data):
        return "refusing to delete Iris data directory"
    iris = iris_repo_root()
    try:
        iris_r = iris.resolve()
    except OSError:
        iris_r = iris
    if t == iris_r or _path_contains(t, iris_r):
        return "refusing to delete Iris repository (or its ancestor)"
    if _path_contains(iris_r, t) and t != iris_r:
        return "refusing to delete inside the Iris repository"
    parts = [p.lower() for p in t.parts]
    if "windows" in parts:
        win_i = parts.index("windows")
        if win_i <= 1:
            return "refusing to delete under Windows"
    protected_leaf = {
        "program files",
        "program files (x86)",
        "programdata",
        "system volume information",
        "$recycle.bin",
    }
    if t.name.lower() in protected_leaf and len(t.parts) <= 2:
        return f"refusing to delete protected path: {t}"
    return None


def resolve_delete_target(
    project_root: str | Path,
    rel_path: str = "",
    *,
    parents: list[Path] | None = None,
) -> tuple[Path, str, str]:
    """(abs_target, rel_or_empty, kind). kind = file|dir|root.

    rel_path 비우면 project_root 전체 삭제. 알려진 project parent 아래 leaf만 허용.
    """
    root = Path(project_root).expanduser().resolve()
    rel = (rel_path or "").replace("\\", "/").strip().lstrip("/")
    if rel:
        if ".." in rel.split("/"):
            raise ValueError("invalid rel_path")
        _root, target, rel_n = resolve_under_root(root, rel)
        if not target.exists():
            raise FileNotFoundError(str(target))
        kind = "file" if target.is_file() or target.is_symlink() else "dir"
    else:
        if not root.exists():
            raise FileNotFoundError(str(root))
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        allowed = parents if parents is not None else default_project_parents()
        under = False
        for parent in allowed:
            try:
                p = parent.resolve()
            except OSError:
                continue
            if root == p:
                raise ValueError(
                    "refusing to delete a project parent itself; pass rel_path or a child folder"
                )
            if _path_contains(p, root):
                under = True
                break
        if not under:
            raise ValueError(
                "whole-root delete requires project_root under a known project parent "
                "(or pass rel_path for a path inside project_root)"
            )
        target = root
        rel_n = ""
        kind = "root"
    reason = dangerous_delete_reason(target)
    if reason:
        raise ValueError(reason)
    return target, rel_n, kind


def delete_project_path(
    project_root: str | Path,
    rel_path: str = "",
    *,
    parents: list[Path] | None = None,
) -> dict:
    """디스크에서 파일·폴더·스캐폴드 루트 삭제. 안전 거절은 ValueError."""
    target, rel_n, kind = resolve_delete_target(
        project_root, rel_path, parents=parents
    )
    if target.is_file() or target.is_symlink():
        target.unlink()
    else:
        shutil.rmtree(target)
    return {
        "deleted": True,
        "path": str(target),
        "rel_path": rel_n,
        "kind": kind,
        "project_root": str(Path(project_root).expanduser().resolve()),
    }


def rename_project_file(project_root: str | Path, src_rel: str, dest_rel: str) -> str:
    """작업 폴더 안에서 이름을 바꾼다. 새 상대경로. 못 바꾸면 빈 문자열."""
    _root, src, src_norm = resolve_under_root(project_root, src_rel)
    _root, dest, dest_norm = resolve_under_root(project_root, dest_rel)
    if src_norm == dest_norm:
        return dest_norm
    if not src.is_file() or dest.exists():
        return ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dest)
    return dest_norm


def write_project_file_stream(
    project_root: str | Path,
    rel_path: str,
    content: str,
    *,
    chunk_chars: int = 32,
    chunk_delay_ms: int = 70,
    on_first_chunk: Callable[[str], None] | None = None,
    pump: Callable[[], None] | None = None,
) -> dict:
    """청크 단위로 파일 내용을 키워 나간다 (레벨 B).

    on_first_chunk: 첫 쓰기 직후 호출(파일 open용).
    pump: 청크 사이 UI 펌프(예: QApplication.processEvents).
    ponytail: sleep은 호출 스레드에서 — HTTP invoke timeout을 넉넉히 둘 것.
    """
    import time

    _root, path, rel = resolve_under_root(project_root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = str(content)
    size = max(1, int(chunk_chars or 80))
    delay = max(0, int(chunk_delay_ms or 0)) / 1000.0
    chunks = _smooth_text_chunks(text, size)
    built = ""
    for i, chunk in enumerate(chunks):
        built += chunk
        path.write_text(built, encoding="utf-8")
        if i == 0 and on_first_chunk is not None:
            on_first_chunk(str(path))
        if i < len(chunks) - 1 and delay > 0:
            if pump is not None:
                pump()
            time.sleep(delay * (1.8 if chunk.endswith("\n") else 1.0))
            if pump is not None:
                pump()
    match = utf8_content_matches(path, text)
    out: dict = {
        "path": str(path),
        "rel_path": rel,
        "bytes": len(text.encode("utf-8")),
        "chunks": len(chunks),
        "chunk_chars": size,
        "chunk_delay_ms": int(chunk_delay_ms or 0),
        "streamed": True,
        "content_match": match,
    }
    if not match:
        out["error"] = "UTF-8 content readback mismatch"
    return out


def _smooth_text_chunks(text: str, size: int) -> list[str]:
    """코드가 IDE에서 자라나는 느낌이 나도록 단어/줄 경계 우선으로 자른다."""
    if not text:
        return [""]
    size = max(1, int(size))
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + size)
        if end < n:
            window = text[i:end]
            split = max(window.rfind("\n"), window.rfind(" "), window.rfind("\t"))
            if split >= max(8, size // 2):
                end = i + split + 1
        chunks.append(text[i:end])
        i = end
    return chunks


_IRIS_TASK_LABEL = "Iris: Run"
_IRIS_EXIT_RE = __import__("re").compile(r"(?m)^IRIS_EXIT:(-?\d+)\s*$")


def _cmd_quote(arg: str) -> str:
    if arg == "":
        return '""'
    if any(ch in arg for ch in ' \t&|<>^%!"'):
        return '"' + arg.replace('"', '""') + '"'
    return arg


def build_iris_terminal_command(argv: list[str], *, shell: str = "") -> str:
    """명령을 통합 터미널에 보여 주면서 .iris/last_run.log에 출력과 IRIS_EXIT를 남긴다.

    shell이 비어 있으면 태스크용 기본값이다. Windows 태스크는 powershell.exe를
    고정하므로 PowerShell. IRIS IDE 통합 터미널은 실제 셸을 넘겨야 한다.
    """
    if not argv:
        raise ValueError("empty argv")
    kind = (shell or "").strip().lower()
    if not kind:
        kind = "powershell" if sys.platform == "win32" else "sh"
    if kind in {"cmd", "cmd.exe"}:
        quoted = " ".join(_cmd_quote(str(a)) for a in argv)
        return (
            "if not exist .iris mkdir .iris\n"
            "del /f /q .iris\\last_run.log 2>nul\n"
            f"{quoted} > .iris\\last_run.log 2>&1\n"
            "echo IRIS_EXIT:%ERRORLEVEL% >> .iris\\last_run.log\n"
            "type .iris\\last_run.log\n"
        )
    if kind in {"powershell", "pwsh", "powershell.exe"}:
        parts: list[str] = []
        for a in argv:
            s = str(a).replace("'", "''")
            parts.append(f"'{s}'")
        invoke = "& " + " ".join(parts)
        return (
            "New-Item -ItemType Directory -Force -Path .iris | Out-Null; "
            "Remove-Item -Force -ErrorAction SilentlyContinue .iris\\last_run.log; "
            f"{invoke} 2>&1 | Tee-Object -FilePath .iris\\last_run.log; "
            "$code = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }; "
            "Add-Content -Path .iris\\last_run.log -Value \"IRIS_EXIT:$code\"; "
            "exit $code"
        )
    import shlex

    cmd = " ".join(shlex.quote(str(a)) for a in argv)
    return (
        "mkdir -p .iris; rm -f .iris/last_run.log; "
        f"{{ {cmd}; }} 2>&1 | tee .iris/last_run.log; "
        'code=${PIPESTATUS[0]}; printf "IRIS_EXIT:%s\\n" "$code" >> .iris/last_run.log; '
        'exit "$code"'
    )


def upsert_iris_run_task(project_root: str | Path, command: str) -> str:
    """`.vscode/tasks.json`에 Iris: Run 태스크 upsert. command는 셸에 그대로.

    Cursor/VS Code: 기본 Build Task → Ctrl+Shift+B 로 통합 터미널 실행.
    """
    import json

    root = Path(project_root).expanduser().resolve()
    vscode = root / ".vscode"
    vscode.mkdir(parents=True, exist_ok=True)
    tasks_path = vscode / "tasks.json"
    data: dict = {"version": "2.0.0", "tasks": []}
    if tasks_path.is_file():
        try:
            raw = json.loads(tasks_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (json.JSONDecodeError, OSError):
            pass
    data.setdefault("version", "2.0.0")
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
        data["tasks"] = tasks
    shell_cfg = (
        {
            "executable": "powershell.exe",
            "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"],
        }
        if sys.platform == "win32"
        # 고정 bash — command가 PIPESTATUS(bash 전용) 문법을 쓰므로 사용자 기본
        # 셸(zsh 등)에 맡기지 않는다.
        else {"executable": "/bin/bash", "args": ["-c"]}
    )
    iris_task = {
        "label": _IRIS_TASK_LABEL,
        "type": "shell",
        "command": command,
        "options": {
            "cwd": "${workspaceFolder}",
            "shell": shell_cfg,
        },
        "problemMatcher": [],
        "group": {"kind": "build", "isDefault": True},
        "presentation": {
            "reveal": "always",
            "focus": True,
            "panel": "dedicated",
            "showReuseMessage": False,
            "clear": True,
        },
    }
    kept: list = []
    for t in tasks:
        if not isinstance(t, dict):
            kept.append(t)
            continue
        if t.get("label") == _IRIS_TASK_LABEL:
            continue
        # ponytail: 다른 태스크의 default build 해제 — Ctrl+Shift+B가 Iris: Run만 타게
        group = t.get("group")
        if isinstance(group, dict) and group.get("kind") == "build" and group.get("isDefault"):
            t = {**t, "group": "build"}
        elif group == "build":
            pass
        kept.append(t)
    kept.append(iris_task)
    data["tasks"] = kept
    tasks_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(tasks_path)


def wait_for_run_log(
    log_path: Path,
    *,
    timeout_sec: float = 60.0,
    stable_sec: float = 0.7,
    pump: Callable[[], None] | None = None,
) -> dict:
    """터미널 tee 로그가 생기고 잠시 안정될 때까지 대기 후 내용 반환."""
    import time

    deadline = time.monotonic() + max(1.0, float(timeout_sec))
    last_size = -1
    stable_since: float | None = None
    while time.monotonic() < deadline:
        if pump is not None:
            pump()
        if log_path.is_file():
            try:
                size = log_path.stat().st_size
            except OSError:
                size = -1
            if size > 0 and size == last_size:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= stable_sec:
                    break
            else:
                stable_since = None
                last_size = size
        time.sleep(0.25)
    text = ""
    if log_path.is_file():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    return {
        "text": text,
        "path": str(log_path),
        "found": bool(text) or log_path.is_file(),
    }


def result_from_terminal_log(
    log_text: str,
    *,
    argv: list[str],
    cwd: str,
    elapsed_sec: float,
) -> dict:
    """로그의 IRIS_EXIT 줄이 있을 때만 종료 코드를 확정한다."""
    match = _IRIS_EXIT_RE.search(log_text or "")
    body = _IRIS_EXIT_RE.sub("", log_text or "").strip()
    confirmed = match is not None
    return {
        "exit_code": int(match.group(1)) if match else None,
        "confirmed": confirmed,
        "stdout": body,
        "stderr": "",
        "elapsed_sec": round(float(elapsed_sec), 3),
        "argv": argv,
        "cwd": cwd,
        "timed_out": False,
        "via": "ide_terminal",
    }


def iris_run_log_path(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    d = root / ".iris"
    d.mkdir(parents=True, exist_ok=True)
    return d / "last_run.log"


_PYTHON_LAUNCHER_NAMES = frozenset({"python", "python.exe", "py", "py.exe"})


def find_project_venv_python(root: str | Path) -> Path | None:
    """bound project_root/.venv 인터프리터. 없으면 None (Iris repo .venv 강제 금지)."""
    root_p = Path(root).expanduser().resolve()
    if sys.platform == "win32":
        cand = root_p / ".venv" / "Scripts" / "python.exe"
    else:
        cand = root_p / ".venv" / "bin" / "python"
    return cand if cand.is_file() else None


def ensure_project_python(root: str | Path, *, create: bool = False) -> Path | None:
    """프로젝트 .venv python. create=False면 없을 때 None; create=True면 venv 생성 후 Path."""
    found = find_project_venv_python(root)
    if found is not None:
        return found
    if not create:
        return None
    root_p = Path(root).expanduser().resolve()
    venv_dir = root_p / ".venv"
    import subprocess

    from iris.system.win_subprocess import no_window_kwargs

    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        cwd=str(root_p),
        **no_window_kwargs(),
    )
    found = find_project_venv_python(root)
    if found is None:
        raise FileNotFoundError(f"venv created but python missing under {venv_dir}")
    return found


def _is_python_launcher_token(token: str) -> bool:
    return Path(str(token)).name.lower() in _PYTHON_LAUNCHER_NAMES


def _is_py_version_selector(token: str) -> bool:
    # Windows `py -3` / `py -3.11` — venv python으로 바꿀 때 제거
    return bool(re.fullmatch(r"-\d+(\.\d+)?", str(token).strip()))


def bind_python_argv(argv: list[str], root: str | Path) -> list[str]:
    """argv[0]이 python/py 런처면 project .venv 절대경로로 교체. node 등은 그대로."""
    if not argv:
        return []
    out = [str(x) for x in argv]
    if not _is_python_launcher_token(out[0]):
        return out
    py = ensure_project_python(root, create=True)
    if py is None:
        raise FileNotFoundError(f"project python unavailable under {root}")
    rest = out[1:]
    name = Path(out[0]).name.lower()
    if name in ("py", "py.exe") and rest and _is_py_version_selector(rest[0]):
        rest = rest[1:]
    return [str(py.resolve()), *rest]


def build_run_command(
    *,
    command: str | list | None = None,
    file: str = "",
    project_root: str | Path | None = None,
) -> list[str]:
    """실행 argv 구성. file만 있으면 확장자로 interpreter 추론."""
    if isinstance(command, list) and command:
        return [str(x) for x in command]
    if isinstance(command, str) and command.strip():
        # ponytail: 단순 공백 split — 따옴표 복잡 파싱은 천장, list args 권장
        import shlex

        try:
            return shlex.split(command.strip(), posix=False)
        except ValueError:
            return command.strip().split()
    rel = (file or "").replace("\\", "/").lstrip("/")
    if not rel:
        raise ValueError("command or file required")
    suffix = Path(rel).suffix.lower()
    if suffix == ".py":
        if project_root is not None:
            py = ensure_project_python(project_root, create=True)
            if py is None:
                raise FileNotFoundError(f"project python unavailable under {project_root}")
            return [str(py.resolve()), rel]
        return ["python", rel]
    if suffix in (".ps1",):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", rel]
    if suffix in (".bat", ".cmd"):
        return ["cmd", "/c", rel]
    if suffix in (".js", ".mjs"):
        return ["node", rel]
    if suffix in (".html", ".htm"):
        raise ValueError(f"use browser preview for static web file: {rel}")
        raise ValueError(
            f"[PROJECT_AUTORUN_UNSUPPORTED_TYPE] 자동 실행에 지원하지 않는 파일 형식입니다: "
            f"{suffix or '(none)'}. Windows Setup 다운로드와 무관합니다."
        )


def is_static_web_file(file: str) -> bool:
    rel = (file or "").replace("\\", "/").lstrip("/")
    return Path(rel).suffix.lower() in (".html", ".htm")


def static_web_file_uri(project_root: str | Path, file: str) -> str:
    """프로젝트 상대 HTML → file:// URI."""
    root = Path(project_root).expanduser().resolve()
    rel = (file or "").replace("\\", "/").lstrip("/")
    path = (root / rel).resolve()
    if root not in path.parents and path != root:
        raise ValueError(f"file escapes project_root: {file}")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path.as_uri()


def infer_dev_server_url(argv: list[str]) -> str | None:
    """터미널 실행 argv에서 흔한 로컬 미리보기 URL 추론."""
    if not argv:
        return None
    parts = [str(a) for a in argv]
    joined = " ".join(parts).lower()
    port: int | None = None
    for i, p in enumerate(parts):
        pl = p.lower()
        if pl in ("--port", "-p", "--listen") and i + 1 < len(parts):
            try:
                port = int(parts[i + 1])
            except ValueError:
                pass
        if pl.startswith("--port="):
            try:
                port = int(pl.split("=", 1)[1])
            except ValueError:
                pass
        # python -m http.server 8080
        if i > 0 and parts[i - 1].lower() == "http.server":
            try:
                port = int(p)
            except ValueError:
                pass
    if "http.server" in joined:
        return f"http://127.0.0.1:{port or 8000}"
    if "vite" in joined:
        return f"http://127.0.0.1:{port or 5173}"
    if "next" in joined or "react-scripts" in joined:
        return f"http://127.0.0.1:{port or 3000}"
    if "npm" in joined and "start" in joined:
        return f"http://127.0.0.1:{port or 3000}"
    if "npx" in joined and "serve" in joined:
        return f"http://127.0.0.1:{port or 3000}"
    if "live-server" in joined:
        return f"http://127.0.0.1:{port or 8080}"
    return None


def open_preview_in_browser(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    try:
        import webbrowser

        return bool(webbrowser.open(url))
    except Exception:
        return False


def run_project_command(
    project_root: str | Path,
    argv: list[str],
    *,
    timeout_sec: float = 60.0,
    input_text: str | None = None,
) -> dict:
    """project_root에서 명령 1회 실행. 이중 실행 금지 — 호출측에서 한 번만."""
    import subprocess
    import time

    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    if not argv:
        raise ValueError("empty command")
    t0 = time.monotonic()
    try:
        from iris.system.win_subprocess import no_window_kwargs

        proc = subprocess.run(  # noqa: S603
            argv,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_sec),
            input=input_text,
            shell=False,
            **no_window_kwargs(),
        )
        elapsed = time.monotonic() - t0
        return {
            "exit_code": int(proc.returncode),
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "elapsed_sec": round(elapsed, 3),
            "argv": argv,
            "cwd": str(root),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - t0
        out = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "exit_code": -1,
            "stdout": out,
            "stderr": (err + f"\n[timeout after {timeout_sec}s]").strip(),
            "elapsed_sec": round(elapsed, 3),
            "argv": argv,
            "cwd": str(root),
            "timed_out": True,
        }


def format_run_log(result: dict) -> str:
    argv = result.get("argv") or []
    cmd = " ".join(str(a) for a in argv)
    lines = [
        f"$ {cmd}",
        f"# cwd: {result.get('cwd')}",
        f"# exit: {result.get('exit_code')}  elapsed: {result.get('elapsed_sec')}s",
        "",
    ]
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout:
        lines.append(stdout.rstrip("\n"))
        lines.append("")
    if stderr:
        lines.append("--- stderr ---")
        lines.append(stderr.rstrip("\n"))
        lines.append("")
    return "\n".join(lines)


_LIST_SKIP_DIRS = frozenset({"node_modules", "__pycache__", "venv", "dist", "build", "out", "target"})

# ponytail: 5만 항목이면 query를 좁히라는 뜻 — 트리 전체 인덱싱은 천장 밖이다.
_LIST_SCAN_CAP = 50_000


def list_workspace_files(
    project_root: str | Path,
    *,
    query: str = "",
    limit: int = 200,
) -> dict:
    """워크스페이스 파일 상대경로 목록. query는 부분일치(대소문자 무시)."""
    import os

    root = Path(project_root).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(str(project_root))
    needle = (query or "").strip().lower().replace("\\", "/")
    cap = max(1, min(int(limit), 1000))
    files: list[str] = []
    scanned = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _LIST_SKIP_DIRS]
        for name in filenames:
            scanned += 1
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/")
            if needle and needle not in rel.lower():
                continue
            files.append(rel)
            if len(files) >= cap:
                truncated = True
                break
        if truncated or scanned >= _LIST_SCAN_CAP:
            truncated = True
            break
    return {
        "root": str(root.resolve()),
        "query": needle,
        "files": files,
        "count": len(files),
        "scanned": scanned,
        "truncated": truncated,
    }


def summarize_run(result: dict, *, max_tail_lines: int = 12) -> dict:
    """채팅용 짧은 요약 + tail (전문은 log/터미널)."""
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    code = result.get("exit_code")
    out_lines = stdout.splitlines()
    err_lines = stderr.splitlines()
    tail_n = max(1, int(max_tail_lines))
    stdout_tail = "\n".join(out_lines[-tail_n:])
    stderr_tail = "\n".join(err_lines[-tail_n:])
    status = "ok" if code == 0 else ("timeout" if result.get("timed_out") else "fail")
    last = ""
    if out_lines:
        last = out_lines[-1][:120]
    elif err_lines:
        last = err_lines[-1][:120]
    bits = [f"exit {code}", status, f"{len(out_lines)} lines out"]
    if err_lines:
        bits.append(f"{len(err_lines)} lines err")
    if last:
        bits.append(f"last: {last}")
    return {
        "summary": " · ".join(bits),
        "stdout_tail": stdout_tail[:2000],
        "stderr_tail": stderr_tail[:2000],
        "status": status,
    }


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        parent = Path(td)
        (parent / "AI-Guitar-Tab-main").mkdir()
        hits = find_similar_projects("ai guitar tab", parents=[parent])
        assert hits, "expected AI-Guitar-Tab-main"
        assert "guitar" in hits[0]["name"].lower()
        best, _amb, reason = pick_similar_project("ai guitar tab", parents=[parent])
        assert reason == "ok" and best is not None
        r = write_project_file_stream(td, "a.txt", "abcdefghij", chunk_chars=3, chunk_delay_ms=0)
        assert Path(r["path"]).read_text(encoding="utf-8") == "abcdefghij"
        assert r["content_match"] is True
        assert r["chunks"] == 4
        w = write_project_file(td, "b.txt", "clean\n")
        assert w["content_match"] is True
        assert not w.get("error")
        Path(w["path"]).write_text("mutated\n", encoding="utf-8")
        assert utf8_content_matches(Path(w["path"]), "clean\n") is False
        assert _smooth_text_chunks("abc def\nghi", 8) == ["abc def\n", "ghi"]
        cmd = build_run_command(file="hello.py")
        assert cmd[0] == "python"
        (parent / "pkg").mkdir()
        (parent / "pkg" / "Iris_adt.py").write_text("x", encoding="utf-8")
        (parent / "node_modules").mkdir()
        (parent / "node_modules" / "Iris_adt.py").write_text("x", encoding="utf-8")
        listed = list_workspace_files(parent, query="iris_adt")
        assert listed["files"] == ["pkg/Iris_adt.py"], listed
        assert list_workspace_files(parent, limit=1)["truncated"] is True
        assert default_generated_rel_path("이미지테스트2를 만들고 코드를 작성", "python") == "iris_generated.py"
        (parent / "iris_generated.py").write_text("print(1)\n", encoding="utf-8")
        moved = rename_project_file(parent, "iris_generated.py", "이미지테스트2.py")
        assert moved == "이미지테스트2.py"
        assert (parent / "이미지테스트2.py").read_text(encoding="utf-8") == "print(1)\n"
        assert not (parent / "iris_generated.py").exists()
        doomed = parent / "doomed-scaffold"
        (doomed / "nested").mkdir(parents=True)
        (doomed / "nested" / "a.txt").write_text("x", encoding="utf-8")
        gone = delete_project_path(doomed, parents=[parent])
        assert gone["deleted"] is True and gone["kind"] == "root"
        assert not doomed.exists()
        kept = parent / "keep-root"
        kept.mkdir()
        (kept / "victim.txt").write_text("y", encoding="utf-8")
        (kept / "sub").mkdir()
        (kept / "sub" / "z.txt").write_text("z", encoding="utf-8")
        assert delete_project_path(kept, "victim.txt")["kind"] == "file"
        assert not (kept / "victim.txt").exists()
        assert delete_project_path(kept, "sub")["kind"] == "dir"
        assert not (kept / "sub").exists()
        assert kept.exists()
        refuse_home = dangerous_delete_reason(Path.home())
        assert refuse_home and "home" in refuse_home
        refuse_iris = dangerous_delete_reason(iris_repo_root())
        assert refuse_iris and "Iris repository" in refuse_iris
        try:
            delete_project_path(Path.home(), parents=[Path.home().parent])
            raise AssertionError("home delete must refuse")
        except ValueError as exc:
            assert "home" in str(exc).lower()
        try:
            delete_project_path(iris_repo_root(), parents=[iris_repo_root().parent])
            raise AssertionError("iris repo delete must refuse")
        except ValueError as exc:
            assert "Iris repository" in str(exc)
        try:
            delete_project_path(parent)  # parent itself is the allowed parent
            raise AssertionError("parent-itself delete must refuse")
        except ValueError as exc:
            assert "project parent" in str(exc) or "rel_path" in str(exc)
    print("project_ops ok", hits[0]["name"], hits[0]["score"], reason)
