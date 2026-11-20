"""Bound workspace inspect — content search and sealed git status/diff.

Read-only. No commit/push. Console children use no_window_kwargs only.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from iris.system.project_ops import _LIST_SKIP_DIRS, resolve_under_root
from iris.system.win_subprocess import no_window_kwargs

_GIT_STATUS_ARGV = ("git", "status", "--porcelain=v1", "-b")
_MATCH_TEXT_CAP = 240
_RAW_TAIL_CAP = 2000
_MAX_FILE_BYTES = 1_048_576


def _report(
    *,
    kind: str,
    root: Path,
    tool: str,
    truncated: bool,
    elapsed_ms: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "root": str(root),
        "tool": tool,
        "truncated": bool(truncated),
        "elapsed_ms": int(elapsed_ms),
        "payload": payload,
    }


def _git_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    # Stop above the bound root so a parent .git (e.g. accidental ~/.git) is ignored.
    env["GIT_CEILING_DIRECTORIES"] = str(root.resolve().parent)
    return env


def _run_hidden(
    argv: list[str] | tuple[str, ...],
    *,
    cwd: Path,
    timeout_sec: float,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    kw: dict[str, Any] = dict(no_window_kwargs())
    if env is not None:
        kw["env"] = env
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        shell=False,
        **kw,
    )


def _ensure_under_root(root: Path, rel: str) -> Path:
    if not (rel or "").strip():
        return root
    _root, path, _rel = resolve_under_root(root, rel)
    return path


def _is_not_a_repo(stderr: str, stdout: str) -> bool:
    blob = f"{stderr}\n{stdout}".lower()
    return "not a git repository" in blob


def _empty_git_status_payload() -> dict[str, Any]:
    return {
        "is_repo": False,
        "branch": None,
        "upstream": None,
        "ahead": None,
        "behind": None,
        "porcelain": [],
        "clean": True,
        "raw_tail": "",
    }


def _parse_branch_header(line: str) -> dict[str, Any]:
    # ## main...origin/main [ahead 1, behind 2]
    body = line[2:].strip() if line.startswith("##") else line.strip()
    branch: str | None = body or None
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    if "..." in body:
        left, right = body.split("...", 1)
        branch = left.strip() or None
        right = right.strip()
        m_ab = re.search(r"\[([^\]]+)\]", right)
        up_part = right
        if m_ab:
            up_part = right[: m_ab.start()].strip()
            meta = m_ab.group(1)
            m_ahead = re.search(r"ahead\s+(\d+)", meta)
            m_behind = re.search(r"behind\s+(\d+)", meta)
            if m_ahead:
                ahead = int(m_ahead.group(1))
            if m_behind:
                behind = int(m_behind.group(1))
        upstream = up_part or None
    elif body.startswith("HEAD"):
        branch = body
    return {
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
    }


def _parse_porcelain_v1(stdout: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    lines = (stdout or "").splitlines()
    header: dict[str, Any] = {
        "branch": None,
        "upstream": None,
        "ahead": None,
        "behind": None,
    }
    entries: list[dict[str, Any]] = []
    raw_lines: list[str] = []
    for line in lines:
        raw_lines.append(line)
        if line.startswith("##"):
            header = _parse_branch_header(line)
            continue
        if len(line) < 3:
            continue
        xy = line[:2]
        rest = line[3:] if line[2:3] == " " else line[2:].lstrip()
        orig_path: str | None = None
        path = rest
        if " -> " in rest:
            left, right = rest.split(" -> ", 1)
            orig_path = left.strip() or None
            path = right.strip()
        entries.append({"xy": xy, "path": path, "orig_path": orig_path})
    raw_tail = "\n".join(raw_lines)
    if len(raw_tail) > _RAW_TAIL_CAP:
        raw_tail = raw_tail[:_RAW_TAIL_CAP]
    return header, entries, raw_tail


def _rg_argv(
    *,
    pattern: str,
    scan: Path,
    glob: str,
    case_insensitive: bool,
    max_matches: int,
) -> list[str]:
    argv = ["rg", "-n", "--no-heading", "--color", "never", "-m", str(max_matches)]
    if case_insensitive:
        argv.append("-i")
    for d in sorted(_LIST_SKIP_DIRS):
        argv.extend(["-g", f"!{d}/**"])
    argv.extend(["-g", "!.*/**"])
    if glob:
        argv.extend(["-g", glob])
    argv.extend(["--", pattern, str(scan)])
    return argv


def _parse_rg_lines(stdout: str, *, root: Path, max_matches: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for line in (stdout or "").splitlines():
        if len(matches) >= max_matches:
            break
        # path:line:text  (Windows drive letters keep first colon)
        m = re.match(r"^(.*?):(\d+):(.*)$", line)
        if not m:
            continue
        raw_path, line_s, text = m.group(1), m.group(2), m.group(3)
        try:
            abs_path = Path(raw_path)
            if not abs_path.is_absolute():
                abs_path = (root / raw_path).resolve()
            else:
                abs_path = abs_path.resolve()
            rel = abs_path.relative_to(root).as_posix()
        except (ValueError, OSError):
            rel = raw_path.replace("\\", "/")
        if len(text) > _MATCH_TEXT_CAP:
            text = text[:_MATCH_TEXT_CAP]
        matches.append({"path": rel, "line": int(line_s), "text": text})
    return matches


def _python_search(
    root: Path,
    scan: Path,
    *,
    pattern: str,
    glob: str,
    case_insensitive: bool,
    max_matches: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        cre = re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError(f"invalid pattern: {exc}") from exc
    matches: list[dict[str, Any]] = []
    scanned = 0
    truncated = False
    if scan.is_file():
        files = [scan]
    else:
        files = []
        for dirpath, dirnames, filenames in os.walk(scan):
            dirnames[:] = [
                d for d in dirnames if not d.startswith(".") and d not in _LIST_SKIP_DIRS
            ]
            for name in filenames:
                files.append(Path(dirpath) / name)
    for path in files:
        if len(matches) >= max_matches:
            truncated = True
            break
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if glob and not (
            fnmatch.fnmatch(path.name, glob) or fnmatch.fnmatch(rel, glob)
        ):
            continue
        scanned += 1
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:8192] or len(data) > _MAX_FILE_BYTES:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if cre.search(line):
                clip = line if len(line) <= _MATCH_TEXT_CAP else line[:_MATCH_TEXT_CAP]
                matches.append({"path": rel, "line": i, "text": clip})
                if len(matches) >= max_matches:
                    truncated = True
                    break
    return matches, scanned, truncated


def search_content(
    root: str | Path,
    *,
    pattern: str,
    path: str = "",
    glob: str = "",
    case_insensitive: bool = True,
    max_matches: int = 80,
    timeout_sec: float = 20.0,
) -> dict[str, Any]:
    """Search file contents under bound root. Prefer rg; else Python walk."""
    t0 = time.perf_counter()
    root_p = Path(root).expanduser().resolve()
    if not root_p.is_dir():
        raise NotADirectoryError(str(root_p))
    pat = str(pattern or "")
    if not pat:
        raise ValueError("pattern required")
    cap = max(1, min(int(max_matches), 2000))
    scan = _ensure_under_root(root_p, str(path or ""))
    if not scan.exists():
        raise FileNotFoundError(str(scan))
    glob_s = str(glob or "")
    matches: list[dict[str, Any]] = []
    scanned = 0
    truncated = False
    tool = "python-grep"
    rg = shutil.which("rg")
    if rg:
        argv = _rg_argv(
            pattern=pat,
            scan=scan,
            glob=glob_s,
            case_insensitive=bool(case_insensitive),
            max_matches=cap,
        )
        argv[0] = rg
        try:
            cp = _run_hidden(argv, cwd=root_p, timeout_sec=timeout_sec)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("rg timed out") from exc
        # 0 = hits, 1 = no matches; other = error
        if cp.returncode in (0, 1):
            matches = _parse_rg_lines(cp.stdout or "", root=root_p, max_matches=cap)
            truncated = len(matches) >= cap
            tool = "rg"
            scanned = len({m["path"] for m in matches})
        else:
            matches, scanned, truncated = _python_search(
                root_p,
                scan,
                pattern=pat,
                glob=glob_s,
                case_insensitive=bool(case_insensitive),
                max_matches=cap,
            )
    else:
        matches, scanned, truncated = _python_search(
            root_p,
            scan,
            pattern=pat,
            glob=glob_s,
            case_insensitive=bool(case_insensitive),
            max_matches=cap,
        )
    files_with = len({m["path"] for m in matches})
    elapsed = int((time.perf_counter() - t0) * 1000)
    return _report(
        kind="search",
        root=root_p,
        tool=tool,
        truncated=truncated,
        elapsed_ms=elapsed,
        payload={
            "pattern": pat,
            "path": str(path or ""),
            "glob": glob_s,
            "matches": matches,
            "match_count": len(matches),
            "files_with_matches": files_with,
            "scanned_files": scanned,
        },
    )


def git_status(
    root: str | Path,
    *,
    timeout_sec: float = 15.0,
) -> dict[str, Any]:
    """Sealed `git status --porcelain=v1 -b`. Soft-ok when not a repo."""
    t0 = time.perf_counter()
    root_p = Path(root).expanduser().resolve()
    if not root_p.is_dir():
        raise NotADirectoryError(str(root_p))
    try:
        cp = _run_hidden(
            _GIT_STATUS_ARGV,
            cwd=root_p,
            timeout_sec=timeout_sec,
            env=_git_env(root_p),
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("git status timed out") from exc
    except FileNotFoundError:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return _report(
            kind="git_status",
            root=root_p,
            tool="git",
            truncated=False,
            elapsed_ms=elapsed,
            payload=_empty_git_status_payload(),
        )
    if cp.returncode != 0 and _is_not_a_repo(cp.stderr or "", cp.stdout or ""):
        elapsed = int((time.perf_counter() - t0) * 1000)
        return _report(
            kind="git_status",
            root=root_p,
            tool="git",
            truncated=False,
            elapsed_ms=elapsed,
            payload=_empty_git_status_payload(),
        )
    if cp.returncode != 0:
        raise OSError((cp.stderr or cp.stdout or "git status failed").strip())
    header, entries, raw_tail = _parse_porcelain_v1(cp.stdout or "")
    elapsed = int((time.perf_counter() - t0) * 1000)
    return _report(
        kind="git_status",
        root=root_p,
        tool="git",
        truncated=False,
        elapsed_ms=elapsed,
        payload={
            "is_repo": True,
            "branch": header.get("branch"),
            "upstream": header.get("upstream"),
            "ahead": header.get("ahead"),
            "behind": header.get("behind"),
            "porcelain": entries,
            "clean": len(entries) == 0,
            "raw_tail": raw_tail,
        },
    )


def git_diff(
    root: str | Path,
    *,
    path: str = "",
    staged: bool = False,
    max_bytes: int = 120_000,
    timeout_sec: float = 20.0,
) -> dict[str, Any]:
    """Sealed `git diff` / `git diff --cached`. Optional jailed path."""
    t0 = time.perf_counter()
    root_p = Path(root).expanduser().resolve()
    if not root_p.is_dir():
        raise NotADirectoryError(str(root_p))
    rel = str(path or "").replace("\\", "/").lstrip("/")
    if rel:
        _ensure_under_root(root_p, rel)
    cap = max(1, int(max_bytes))
    argv: list[str] = ["git", "diff", "--no-color"]
    if staged:
        argv.append("--cached")
    if rel:
        argv.extend(["--", rel])
    git_env = _git_env(root_p)
    try:
        cp = _run_hidden(argv, cwd=root_p, timeout_sec=timeout_sec, env=git_env)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("git diff timed out") from exc
    except FileNotFoundError:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return _report(
            kind="git_diff",
            root=root_p,
            tool="git",
            truncated=False,
            elapsed_ms=elapsed,
            payload={
                "is_repo": False,
                "path": rel,
                "staged": bool(staged),
                "patch": "",
                "truncated": False,
                "stat": "",
            },
        )
    if cp.returncode != 0 and _is_not_a_repo(cp.stderr or "", cp.stdout or ""):
        elapsed = int((time.perf_counter() - t0) * 1000)
        return _report(
            kind="git_diff",
            root=root_p,
            tool="git",
            truncated=False,
            elapsed_ms=elapsed,
            payload={
                "is_repo": False,
                "path": rel,
                "staged": bool(staged),
                "patch": "",
                "truncated": False,
                "stat": "",
            },
        )
    if cp.returncode not in (0, 1):
        raise OSError((cp.stderr or cp.stdout or "git diff failed").strip())
    patch = cp.stdout or ""
    truncated = False
    raw_bytes = patch.encode("utf-8", errors="replace")
    if len(raw_bytes) > cap:
        truncated = True
        patch = raw_bytes[:cap].decode("utf-8", errors="replace")
    stat = ""
    stat_argv = ["git", "diff", "--no-color", "--stat"]
    if staged:
        stat_argv.append("--cached")
    if rel:
        stat_argv.extend(["--", rel])
    try:
        scp = _run_hidden(
            stat_argv,
            cwd=root_p,
            timeout_sec=min(timeout_sec, 10.0),
            env=git_env,
        )
        if scp.returncode in (0, 1):
            stat = (scp.stdout or "")[:4000]
    except (OSError, subprocess.TimeoutExpired):
        stat = ""
    elapsed = int((time.perf_counter() - t0) * 1000)
    return _report(
        kind="git_diff",
        root=root_p,
        tool="git",
        truncated=truncated,
        elapsed_ms=elapsed,
        payload={
            "is_repo": True,
            "path": rel,
            "staged": bool(staged),
            "patch": patch,
            "truncated": truncated,
            "stat": stat,
        },
    )
