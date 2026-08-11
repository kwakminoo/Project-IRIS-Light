"""프로젝트 폴더 찾기·스캐폴드·파일 쓰기 (Iris Control용).

ponytail: difflib 유사도 + 알려진 부모 디렉터리만 스캔.
"""

from __future__ import annotations

import re
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


def write_project_file(project_root: str | Path, rel_path: str, content: str) -> dict:
    _root, path, rel = resolve_under_root(project_root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": str(path), "rel_path": rel, "bytes": len(content.encode("utf-8"))}


def is_code_reveal_request(text: str) -> bool:
    s = (text or "").lower()
    code_words = ("코드", "프로그램", "파일", "script", "code", "program", "app")
    make_words = ("만들", "작성", "짜", "구현", "생성", "write", "create", "make", "build")
    if is_run_request(s) or "구구단" in s:
        return True
    return any(w in s for w in make_words) and any(w in s for w in code_words)


def is_run_request(text: str) -> bool:
    s = (text or "").lower()
    return any(w in s for w in ("실행", "출력", "돌려", "run", "execute", "print"))


def extract_first_code_block(text: str) -> dict | None:
    match = re.search(r"```([^\n`]*)\n(.*?)```", text or "", flags=re.DOTALL)
    if not match:
        return None
    info = (match.group(1) or "").strip()
    code = (match.group(2) or "").strip("\n")
    if not code.strip():
        return None
    lang = (info.split() or [""])[0].lower()
    return {"lang": lang, "code": code}


def default_generated_rel_path(prompt: str, lang: str) -> str:
    stem = "gugudan" if "구구단" in (prompt or "") else "iris_generated"
    suffixes = {
        "python": ".py",
        "py": ".py",
        "javascript": ".js",
        "js": ".js",
        "typescript": ".ts",
        "ts": ".ts",
    }
    return stem + suffixes.get((lang or "").lower(), ".py")


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
    return {
        "path": str(path),
        "rel_path": rel,
        "bytes": len(text.encode("utf-8")),
        "chunks": len(chunks),
        "chunk_chars": size,
        "chunk_delay_ms": int(chunk_delay_ms or 0),
        "streamed": True,
    }


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


def build_iris_terminal_command(argv: list[str]) -> str:
    """명령을 통합 터미널에 보여 주면서 .iris/last_run.log에도 tee.

    이중 실행 없음 — 터미널 1회만. Iris는 로그를 읽어 채팅 요약.
    Windows: PowerShell. macOS/Linux: bash(PIPESTATUS로 종료코드 보존).
    """
    if not argv:
        raise ValueError("empty argv")
    if sys.platform == "win32":
        parts: list[str] = []
        for a in argv:
            s = str(a).replace("'", "''")
            parts.append(f"'{s}'")
        invoke = "& " + " ".join(parts)
        # $LASTEXITCODE: native 명령 종료코드
        return (
            "New-Item -ItemType Directory -Force -Path .iris | Out-Null; "
            "Remove-Item -Force -ErrorAction SilentlyContinue .iris\\last_run.log; "
            f"$out = {invoke} 2>&1 | Tee-Object -FilePath .iris\\last_run.log; "
            "if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE } else { exit 0 }"
        )
    import shlex

    cmd = " ".join(shlex.quote(str(a)) for a in argv)
    return (
        "mkdir -p .iris; rm -f .iris/last_run.log; "
        f"{{ {cmd}; }} 2>&1 | tee .iris/last_run.log; "
        "exit ${PIPESTATUS[0]}"
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
    """tee 로그 텍스트를 run_project_command 결과 형태로."""
    # stderr 구분 없이 tee 됨 — 전체를 stdout으로, 실패 추정은 비어있음/traceback
    low = (log_text or "").lower()
    failed = "traceback (most recent call last)" in low or "error:" in low
    return {
        "exit_code": 1 if failed and "traceback" in low else 0,
        "stdout": log_text or "",
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


def build_run_command(
    *,
    command: str | list | None = None,
    file: str = "",
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
        return ["python", rel]
    if suffix in (".ps1",):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", rel]
    if suffix in (".bat", ".cmd"):
        return ["cmd", "/c", rel]
    if suffix in (".js", ".mjs"):
        return ["node", rel]
    raise ValueError(f"unsupported file type for auto-run: {suffix or '(none)'}")


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
        assert r["chunks"] == 4
        assert _smooth_text_chunks("abc def\nghi", 8) == ["abc def\n", "ghi"]
        cmd = build_run_command(file="hello.py")
        assert cmd[0] == "python"
    print("project_ops ok", hits[0]["name"], hits[0]["score"], reason)
