"""GitHub URL → Hermes MCP config / skills 폴더 설치.

채팅에서 주소와 함께 MCP 연결·Skill 적용을 요청하면, Iris Agent 홈
(`iris_agent_home()` / config.yaml·skills/) 에만 기록한다.
저장소 README의 임의 셸은 실행하지 않는다.

ponytail: GitHub 목록은 깊이 3·25회·파일 40개·2MB. 로컬 빌드가 필요한 서버는
여기서 거부하고, 그때 clone 설치를 추가한다.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARG_OK = re.compile(r"^[@A-Za-z0-9_./:+~=-]+$")
_KV_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\s*[=:]\s*(\S+)")
_PLACEHOLDER = re.compile(
    r"^(?:<[^>]+>|\$\{[^}]+\}|YOUR_[A-Z0-9_]*|changeme|xxx+|token|none|null)?$",
    re.IGNORECASE,
)
_ALLOWED_CMDS = {"npx", "uvx", "uv", "python", "python3", "py", "node"}
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
}
_MANIFESTS = {
    "skill.md",
    "mcp.json",
    ".mcp.json",
    "server.json",
    "package.json",
    "pyproject.toml",
    "readme.md",
}
_MAX_FILES = 40
_MAX_BYTES = 2_000_000
_MAX_FILE = 256_000
_MAX_LISTINGS = 25


@dataclass(frozen=True)
class ExtensionRequest:
    url: str
    kind: str  # mcp | skill | auto


@dataclass
class RepoSnapshot:
    label: str
    files: dict[str, str] = field(default_factory=dict)
    dirs: dict[str, list[str]] = field(default_factory=dict)
    read: Callable[[str], str] | None = None


@dataclass
class McpSpec:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    missing_env: list[str]
    script: str | None = None
    need_dir: bool = False
    source: str = ""


@dataclass
class InstallResult:
    status: str
    message: str
    mcp_names: list[str] = field(default_factory=list)
    skill_names: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    called_tool: str = ""
    call_preview: str = ""
    missing_env: list[str] = field(default_factory=list)
    need_dir: bool = False
    mcp_added: bool = False
    config_path: str = ""
    skill_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def hermes_home() -> Path:
    from iris.system.hermes_iris_control_sync import hermes_home as _home

    return _home()


def parse_extension_request(text: str) -> ExtensionRequest | None:
    """GitHub 주소 + 연결/적용 요청만. 일반 '추가해줘'는 가로채지 않는다."""
    raw_url = _first_github_url(text)
    if not raw_url or parse_github_url(raw_url) is None:
        return None
    outside = _URL_RE.sub(" ", text or "").lower()
    has_mcp = "mcp" in outside
    has_skill = "skill" in outside or "스킬" in outside
    use_phrase = "사용할 수 있게" in outside or "쓸 수 있게" in outside
    strong = any(w in outside for w in ("연결", "적용", "설치", "등록")) or bool(
        re.search(r"\b(connect|install|enable)\b", outside)
    )
    add = "추가" in outside or bool(re.search(r"\badd\b", outside))
    if has_mcp and has_skill and (strong or add or use_phrase):
        kind = "auto"
    elif has_mcp and (strong or add or use_phrase):
        kind = "mcp"
    elif has_skill and (strong or add or use_phrase):
        kind = "skill"
    elif use_phrase or strong:
        kind = "auto"
    else:
        return None
    return ExtensionRequest(url=raw_url, kind=kind)


def parse_secret_reply(text: str, missing: list[str]) -> dict[str, str] | None:
    want = [k for k in missing if _ENV_KEY.match(k)]
    if not want:
        return None
    found: dict[str, str] = {}
    for key, val in _KV_RE.findall(text or ""):
        if key in want:
            clean = _clean_secret(val)
            if clean:
                found[key] = clean
    if found:
        return found
    token = (text or "").strip().strip('"').strip("'")
    if (
        len(want) == 1
        and token
        and " " not in token
        and "\n" not in token
        and not token.lower().startswith("http")
        and _clean_secret(token)
    ):
        return {want[0]: _clean_secret(token)}
    return None


def parse_dir_reply(text: str) -> str | None:
    body = (text or "").strip()
    m = re.search(r"(?:디렉터리|경로|directory|path)\s*[:=]\s*(.+)", body, re.IGNORECASE)
    if m:
        body = m.group(1).strip()
    body = body.strip().strip('"').strip("'")
    if not body or "\n" in body or body.lower().startswith("http"):
        return None
    try:
        path = Path(body).expanduser().resolve()
    except OSError:
        return None
    if path.is_dir():
        return str(path)
    return None


def parse_github_url(url: str) -> tuple[str, str, str, str] | None:
    parsed = urllib.parse.urlparse((url or "").strip().rstrip(").,;"))
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "github.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not _SAFE_PART.match(owner) or not _SAFE_PART.match(repo):
        return None
    ref, sub = "", ""
    if len(parts) >= 3:
        if parts[2] not in ("tree", "blob") or len(parts) < 4:
            return None
        ref = parts[3]
        sub = "/".join(parts[4:])
        if not _SAFE_PART.match(ref) or not _safe_rel(sub) and sub:
            return None
    return owner, repo, ref, sub


def install_from_request(
    req: ExtensionRequest,
    *,
    home: Path | None = None,
    secrets: dict[str, str] | None = None,
    directory: str | None = None,
    fetch: Callable[[str], RepoSnapshot] | None = None,
    probe_timeout: float = 20.0,
    project_root: str | None = None,
) -> InstallResult:
    if (project_root or "").strip():
        root = Path(project_root).expanduser().resolve()
        if not root.is_dir():
            return InstallResult("refused", "열린 프로젝트 폴더가 없습니다.")
        home = root / ".iris"
        home.mkdir(parents=True, exist_ok=True)
        (home / "PROJECT").write_text(str(root), encoding="utf-8")
    else:
        home = (home or hermes_home()).expanduser()
    secrets = _accepted_secrets(secrets or {})
    try:
        snap = (fetch or fetch_github)(req.url)
    except Exception as exc:  # noqa: BLE001
        return InstallResult("failed", _redact(str(exc), secrets) or "저장소를 읽지 못했습니다.")

    specs = _mcp_specs(snap, secrets)
    skills = _skill_files(snap)
    want_mcp = req.kind in ("mcp", "auto")
    want_skill = req.kind in ("skill", "auto")
    notes: list[str] = []
    result = InstallResult("refused", "")

    if want_skill and not skills and req.kind == "skill":
        if not isinstance(specs, str) and specs:
            return InstallResult(
                "refused",
                "이 저장소는 Skill(SKILL.md)이 없고 MCP 설정만 있습니다. "
                + ", ".join(s.name for s in specs),
            )
        return InstallResult("refused", _not_extension_message(specs))

    if want_mcp and req.kind == "mcp" and (isinstance(specs, str) or not specs):
        if skills:
            return InstallResult(
                "refused",
                "이 저장소는 MCP 설정이 없고 Skill만 있습니다: "
                + ", ".join(_skill_name(snap, p) for p in skills),
            )
        detail = specs if isinstance(specs, str) else ""
        return InstallResult("refused", detail or _not_extension_message(specs))

    if want_skill:
        _apply_skills(home, snap, skills, notes, result)
    if want_mcp and not isinstance(specs, str) and specs:
        _apply_mcps(
            home,
            snap,
            specs,
            secrets,
            directory,
            probe_timeout,
            notes,
            result,
        )
    elif want_mcp and isinstance(specs, str) and req.kind == "auto":
        notes.append(specs)
        if result.status == "refused":
            result.status = "failed"

    if not notes and result.status == "refused":
        result.message = _not_extension_message(specs)
        return result
    result.message = _redact("\n".join(n for n in notes if n), secrets)
    if result.status == "refused" and result.mcp_added:
        result.status = "installed"
    return result


def fetch_github(url: str, *, timeout: float = 20.0) -> RepoSnapshot:
    parsed = parse_github_url(url)
    if parsed is None:
        raise RuntimeError("GitHub 저장소 주소가 아닙니다.")
    owner, repo, ref, sub = parsed
    if not ref:
        meta = _gh_json(f"https://api.github.com/repos/{owner}/{repo}", timeout)
        ref = str(meta.get("default_branch") or "main")
    snap = RepoSnapshot(label=f"{owner}/{repo}/{sub}".strip("/"))
    seen = 0
    total = 0

    def remember(rel: str, text: str) -> None:
        nonlocal total
        if rel in snap.files or len(snap.files) >= _MAX_FILES:
            return
        raw = text.encode("utf-8", errors="replace")
        if len(raw) > _MAX_FILE or total + len(raw) > _MAX_BYTES:
            return
        snap.files[rel] = text
        total += len(raw)

    def read(rel: str) -> str:
        if rel in snap.files:
            return snap.files[rel]
        repo_path = f"{sub}/{rel}".strip("/")
        text = _download_file(owner, repo, repo_path, ref, timeout)
        remember(rel, text)
        return text

    snap.read = read

    def walk(repo_path: str, rel_dir: str, depth: int) -> None:
        nonlocal seen
        if seen >= _MAX_LISTINGS or depth > 3:
            return
        seen += 1
        data = _gh_json(_contents_url(owner, repo, repo_path, ref), timeout)
        if isinstance(data, dict) and data.get("type") == "file":
            name = str(data.get("name") or "")
            if _interesting(name) and int(data.get("size") or 0) <= _MAX_FILE:
                remember(rel_dir or name, _decode_content(data))
            return
        if not isinstance(data, list):
            raise RuntimeError("GitHub 목록 형식이 예상과 다릅니다.")
        names: list[str] = []
        for ent in data:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "")
            if not name or name in _SKIP_DIRS:
                continue
            names.append(name)
        snap.dirs[rel_dir] = names
        for ent in data:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "")
            if not name or name in _SKIP_DIRS:
                continue
            typ = str(ent.get("type") or "")
            child_rel = f"{rel_dir}/{name}".strip("/")
            child_repo = str(ent.get("path") or f"{repo_path}/{name}".strip("/"))
            if typ == "file" and _interesting(name) and int(ent.get("size") or 0) <= _MAX_FILE:
                if name.lower() in _MANIFESTS or name.lower() == "skill.md":
                    remember(child_rel, _download_file(owner, repo, child_repo, ref, timeout))
            elif typ == "dir" and _descend(name, depth):
                walk(child_repo, child_rel, depth + 1)

    walk(sub, "", 0)
    return snap


def load_state(home: Path) -> dict[str, Any]:
    """디스크에 남아 있는 MCP 이름·Skill 이름. 재시작 후에도 같은 함수로 읽힌다."""
    cfg = _read_config(home)
    servers = cfg.get("mcp_servers") if isinstance(cfg.get("mcp_servers"), dict) else {}
    skills: list[str] = []
    root = home / "skills"
    if root.is_dir():
        for path in sorted(root.rglob("SKILL.md")):
            skills.append(path.parent.name)
    return {
        "mcp": list(servers.keys()),
        "skills": skills,
        "config": str(home / "config.yaml"),
    }


def _apply_skills(
    home: Path,
    snap: RepoSnapshot,
    skills: list[str],
    notes: list[str],
    result: InstallResult,
) -> None:
    if not skills:
        return
    installed = 0
    already = 0
    for rel in skills[:5]:
        text = _file(snap, rel)
        if text is None:
            notes.append(f"Skill 파일을 읽지 못했습니다: {rel}")
            result.status = "failed"
            continue
        name = _skill_name(snap, rel)
        if not name:
            notes.append(f"Skill 이름이 비어 있습니다: {rel}")
            result.status = "failed"
            continue
        dest = home / "skills" / "custom" / name
        existing = dest / "SKILL.md"
        if existing.is_file() and existing.read_text(encoding="utf-8", errors="replace") == text:
            already += 1
            result.skill_names.append(name)
            result.skill_paths.append(str(existing))
            continue
        if existing.is_file():
            notes.append(f"Skill '{name}'이 이미 다른 내용으로 있어 덮어쓰지 않았습니다.")
            result.status = "failed"
            continue
        prefix = rel.rsplit("/", 1)[0] if "/" in rel else ""
        try:
            _write_skill_tree(dest, snap, prefix)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Skill '{name}' 저장 실패: {exc}")
            result.status = "failed"
            shutil.rmtree(dest, ignore_errors=True)
            continue
        installed += 1
        result.skill_names.append(name)
        result.skill_paths.append(str(dest / "SKILL.md"))
    if installed:
        notes.append(
            "Skill "
            + ", ".join(f"'{n}'" for n in result.skill_names)
            + "을 설치했습니다. Hermes skills 폴더에서 다음 요청부터 인식합니다.\n"
            + "\n".join(result.skill_paths)
        )
        if result.status == "refused":
            result.status = "installed"
    elif already and result.status != "failed":
        notes.append(
            "Skill " + ", ".join(f"'{n}'" for n in result.skill_names) + "은 이미 설치되어 있습니다."
        )
        result.status = "already"


def _apply_mcps(
    home: Path,
    snap: RepoSnapshot,
    specs: list[McpSpec],
    secrets: dict[str, str],
    directory: str | None,
    probe_timeout: float,
    notes: list[str],
    result: InstallResult,
) -> None:
    for spec in specs[:3]:
        current = _current_server(home, spec.name)
        if current is not None and _same_identity(current, spec, directory):
            result.mcp_names.append(spec.name)
            notes.append(f"MCP '{spec.name}'은 이미 같은 설정으로 연결되어 있습니다.")
            if result.status == "refused":
                result.status = "already"
            continue
        if current is not None:
            notes.append(f"MCP '{spec.name}'은 다른 명령으로 이미 등록되어 있어 덮어쓰지 않았습니다.")
            result.status = "failed"
            continue
        missing = [k for k in spec.missing_env if k not in secrets]
        if missing:
            result.missing_env = missing
            result.need_dir = spec.need_dir and not directory
            result.status = "needs_input"
            shown = ", ".join(missing)
            notes.append(f"이 MCP는 {shown} 환경변수가 필요합니다. 값을 입력해주세요.")
            if result.need_dir:
                notes.append("접근할 디렉터리 경로도 이어서 입력해주세요.")
            return
        if spec.need_dir and not directory:
            result.need_dir = True
            result.status = "needs_input"
            notes.append(
                f"MCP '{spec.name}'은 접근할 디렉터리 경로가 필요합니다. 경로를 입력해주세요."
            )
            return
        block, spawn, err = _prepare_block(home, snap, spec, secrets, directory)
        if err or block is None or spawn is None:
            notes.append(err or f"MCP '{spec.name}' 구성을 만들지 못했습니다.")
            result.status = "failed"
            continue
        if spec.script and _materialize_script(home, spec.name, snap, spec.script) is None:
            notes.append(f"MCP '{spec.name}' 스크립트를 저장소에서 찾지 못했습니다: {spec.script}")
            result.status = "failed"
            continue
        spawn_timeout = float(probe_timeout)
        if _cmd_base(str(spawn[0])) in ("npx", "uvx", "uv", "npm", "node"):
            spawn_timeout = max(spawn_timeout, 180.0)
        probe = probe_mcp(
            spawn[0],
            spawn[1:],
            block.get("env") if isinstance(block.get("env"), dict) else {},
            cwd=str(block.get("cwd") or ""),
            timeout=spawn_timeout,
            startup_timeout=spawn_timeout,
            rpc_timeout=30.0,
            secrets=secrets,
        )
        if not probe.get("ok"):
            notes.append(f"MCP '{spec.name}' 연결 실패: {probe.get('detail')}")
            result.status = "failed"
            _discard_sources(home, spec.name)
            continue
        try:
            _write_server(home, spec.name, block)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"MCP '{spec.name}' 설정 저장 실패: {exc}")
            result.status = "failed"
            _discard_sources(home, spec.name)
            continue
        tools = [str(t) for t in probe.get("tools") or []]
        result.mcp_names.append(spec.name)
        result.tools.extend(tools)
        result.mcp_added = True
        result.config_path = str(home / ("mcp.json" if _project_store(home) else "config.yaml"))
        if probe.get("called_tool"):
            result.called_tool = str(probe.get("called_tool"))
            result.call_preview = str(probe.get("call_preview") or "")
        tool_s = ", ".join(tools) if tools else "(도구 없음)"
        called = ""
        if result.called_tool:
            called = f" '{result.called_tool}' 호출 결과: {result.call_preview or 'ok'}."
        notes.append(
            f"MCP '{spec.name}'을 연결했습니다. 도구: {tool_s}.{called} "
            f"설정: {result.config_path}"
        )
        if result.status in ("refused", "already"):
            result.status = "installed"


def probe_mcp(
    command: str,
    args: list[str],
    env: dict[str, Any],
    *,
    cwd: str = "",
    timeout: float = 20.0,
    startup_timeout: float | None = None,
    rpc_timeout: float | None = None,
    secrets: dict[str, str] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """stdio initialize + tools/list + 도구 호출. 끝나면 프로세스를 죽인다.

    tool_calls 가 없으면 필수 인자가 없는 도구를 한 번 호출한다.
    허용 디렉터리는 args 이고, cwd 로 넣지 않는다.
    """
    from iris.system.executable_resolve import resolve_executable

    secrets = secrets or {}
    out: dict[str, Any] = {
        "ok": False,
        "tools": [],
        "detail": "",
        "called_tool": "",
        "call_preview": "",
        "command": command,
        "args": list(args),
        "resolved": "",
        "cwd": cwd or "",
        "stderr": "",
        "tool_results": [],
        "pid": None,
        "returncode": None,
        "frames": [],
    }
    frames: list[str] = out["frames"]
    resolved = resolve_executable(command)
    if not resolved:
        out["detail"] = f"실행 파일을 찾지 못했습니다: {Path(command).name}"
        return out
    out["resolved"] = resolved
    spawn_cwd: str | None = None
    if cwd:
        cwd_path = Path(cwd).expanduser()
        if not cwd_path.is_dir():
            out["detail"] = f"cwd가 디렉터리가 아닙니다: {cwd}"
            return out
        spawn_cwd = str(cwd_path)
        out["cwd"] = spawn_cwd
    child_env = os.environ.copy()
    for key, val in env.items():
        if _ENV_KEY.match(str(key)):
            child_env[str(key)] = str(val)
    child_env["PYTHONUNBUFFERED"] = "1"
    bin_dir = str(Path(resolved).parent)
    path_val = child_env.get("PATH", "")
    path_parts = [p for p in path_val.split(os.pathsep) if p]
    if os.path.normcase(bin_dir) not in {os.path.normcase(p) for p in path_parts}:
        child_env["PATH"] = bin_dir + (os.pathsep + path_val if path_val else "")
    stderr_chunks: list[str] = []
    proc: subprocess.Popen | None = None
    drain: threading.Thread | None = None
    try:
        from iris.system.win_subprocess import no_window_kwargs

        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        proc = subprocess.Popen(
            [resolved, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=spawn_cwd,
            env=child_env,
            **no_window_kwargs(extra_creationflags=flags),
        )
        assert proc.stdin and proc.stdout and proc.stderr

        def _drain() -> None:
            try:
                while proc and proc.stderr:
                    chunk = proc.stderr.read(4096)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk.decode("utf-8", errors="replace"))
            except Exception:
                pass

        drain = threading.Thread(target=_drain, daemon=True)
        drain.start()
        out["pid"] = proc.pid
        startup = float(startup_timeout if startup_timeout is not None else timeout)
        rpc = float(rpc_timeout if rpc_timeout is not None else timeout)
        started = time_monotonic()
        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "iris-light", "version": "0"},
            },
        }
        out["initialize_request"] = init
        _send(proc, init)
        first, why = _wait_response(
            proc, 1, startup, phase="initialize", stderr_chunks=stderr_chunks, frames=frames
        )
        out["initialize_sec"] = round(time_monotonic() - started, 3)
        if not first or "result" not in first:
            out["detail"] = why or _fail_detail(proc, first, stderr_chunks, secrets, phase="initialize")
            return out
        out["initialize"] = first.get("result")
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed_at = time_monotonic()
        listed, why = _wait_response(
            proc, 2, rpc, phase="tools/list", stderr_chunks=stderr_chunks, frames=frames
        )
        out["tools_list_sec"] = round(time_monotonic() - listed_at, 3)
        tools = ((listed or {}).get("result") or {}).get("tools") if isinstance(listed, dict) else None
        if not isinstance(tools, list):
            out["detail"] = why or _fail_detail(proc, listed, stderr_chunks, secrets, phase="tools/list")
            return out
        names = [str(t.get("name")) for t in tools if isinstance(t, dict) and t.get("name")]
        out["tools"] = names
        if tool_calls:
            results: list[dict[str, Any]] = []
            for offset, call in enumerate(tool_calls):
                name = str(call.get("name") or "")
                arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 3 + offset,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    },
                )
                called_msg, why = _wait_response(
                    proc,
                    3 + offset,
                    rpc,
                    phase=f"tools/call {name}",
                    stderr_chunks=stderr_chunks,
                    frames=frames,
                )
                text = _call_text(called_msg)
                if text is None:
                    out["detail"] = why or _fail_detail(
                        proc, called_msg, stderr_chunks, secrets, phase=f"tools/call {name}"
                    )
                    out["tool_results"] = results
                    return out
                redacted = _redact(text, secrets)
                results.append({"name": name, "text": redacted[:2000]})
            out["tool_results"] = results
            if results:
                out["called_tool"] = str(results[-1]["name"])
                out["call_preview"] = str(results[-1]["text"])[:180]
        else:
            called = _callable_tool(tools)
            if called:
                _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": called, "arguments": {}},
                    },
                )
                called_msg, why = _wait_response(
                    proc,
                    3,
                    rpc,
                    phase=f"tools/call {called}",
                    stderr_chunks=stderr_chunks,
                    frames=frames,
                )
                preview = _call_preview(called_msg)
                if preview is None:
                    out["detail"] = why or _fail_detail(
                        proc, called_msg, stderr_chunks, secrets, phase=f"tools/call {called}"
                    )
                    return out
                out["called_tool"] = called
                out["call_preview"] = _redact(preview, secrets)[:180]
        out["handshake_sec"] = round(time_monotonic() - started, 3)
        out["ok"] = True
        out["detail"] = "connected"
        return out
    except Exception as exc:  # noqa: BLE001
        out["detail"] = _redact(
            f"{exc} (resolved={out.get('resolved') or command})",
            secrets,
        )[:300]
        return out
    finally:
        if proc is not None:
            out["returncode"] = proc.poll()
            _kill_tree(proc)
        if drain is not None:
            drain.join(timeout=2)
        out["stderr"] = "".join(stderr_chunks).strip()[:800]


def _prepare_block(
    home: Path,
    snap: RepoSnapshot,
    spec: McpSpec,
    secrets: dict[str, str],
    directory: str | None,
) -> tuple[dict[str, Any] | None, list[str] | None, str]:
    command, args, err = _normalize_command(spec.command, list(spec.args))
    if err:
        return None, None, f"MCP '{spec.name}' 거부: {err}"
    env = dict(spec.env)
    for key in spec.missing_env:
        env[key] = secrets[key]
    block: dict[str, Any] = {
        "command": command,
        "args": args,
        "enabled": True,
        "timeout": 120,
        "connect_timeout": 60,
    }
    if env:
        block["env"] = env
    spawn_cmd = command
    if spec.script:
        rel = _safe_rel(spec.script)
        if rel is None or _file(snap, spec.script) is None:
            return None, None, f"MCP '{spec.name}' 스크립트를 저장소에서 찾지 못했습니다: {spec.script}"
        root = home / "mcp-sources" / _safe_name(spec.name)
        script = root / rel.as_posix()
        block["cwd"] = str(root)
        block["command"] = sys.executable if _cmd_base(command) in ("python", "python3", "py") else command
        if _cmd_base(block["command"]) in ("python", "python3", "py") or Path(block["command"]) == Path(sys.executable):
            block["command"] = sys.executable
            block["args"] = ["-u", str(script)]
            env = dict(block.get("env") or {})
            env.setdefault("PYTHONUNBUFFERED", "1")
            env.setdefault("PYTHONIOENCODING", "utf-8")
            block["env"] = env
        else:
            replaced = []
            for arg in args:
                if arg.replace("\\", "/").endswith(spec.script.replace("\\", "/")):
                    replaced.append(str(script))
                else:
                    replaced.append(arg)
            block["args"] = replaced
        spawn_cmd = str(block["command"])
    if directory:
        block["args"] = [*list(block["args"]), directory]
    return block, [spawn_cmd, *list(block["args"])], ""


def _current_server(home: Path, name: str) -> dict[str, Any] | None:
    servers = _read_config(home).get("mcp_servers")
    if not isinstance(servers, dict):
        return None
    current = servers.get(_safe_name(name))
    return current if isinstance(current, dict) else None


def _same_identity(current: dict[str, Any], spec: McpSpec, directory: str | None) -> bool:
    """이미 등록된 서버면 비밀값을 다시 묻지 않는다. 명령이 다르면 덮어쓰지 않는다."""
    command, args, err = _normalize_command(spec.command, list(spec.args))
    if err:
        return False
    if spec.script:
        command = sys.executable
        root = Path(str(current.get("cwd") or ""))
        rel = _safe_rel(spec.script)
        if rel is None or not root:
            return False
        args = ["-u", str(root / rel.as_posix())]
    if directory:
        args = [*args, directory]
    if str(current.get("command") or "") != command and _arg_key(str(current.get("command") or "")) != _arg_key(command):
        return False
    cur_args = [str(a) for a in current.get("args") or []]
    if directory:
        return _same_args(cur_args, args, prefix=False)
    if not _same_args(cur_args, args, prefix=True):
        return False
    saved = current.get("env") if isinstance(current.get("env"), dict) else {}
    for key in spec.missing_env:
        if not str(saved.get(key) or "").strip():
            return False
    return True


def _arg_key(value: str) -> str:
    text = str(value or "")
    looks_path = (len(text) >= 3 and text[1] == ":") or text.startswith("\\\\") or (
        text.startswith("/") and Path(text).is_absolute()
    )
    if not looks_path:
        return text
    try:
        return str(Path(text).resolve()).lower()
    except OSError:
        return text.lower()


def _same_args(current: list[str], expected: list[str], *, prefix: bool) -> bool:
    cur = [_arg_key(a) for a in current]
    exp = [_arg_key(a) for a in expected]
    if prefix:
        return cur[: len(exp)] == exp
    return cur == exp


def _materialize_script(home: Path, name: str, snap: RepoSnapshot, script: str) -> Path | None:
    rel = _safe_rel(script)
    if rel is None:
        return None
    root = home / "mcp-sources" / _safe_name(name)
    parent = "" if rel.parent.as_posix() in ("", ".") else rel.parent.as_posix()
    names = list(snap.dirs.get(parent) or [])
    if not names:
        names = [
            p.rsplit("/", 1)[-1]
            for p in snap.files
            if (parent == "" and "/" not in p) or p.rsplit("/", 1)[0] == parent
        ]
    if rel.name not in names:
        names.append(rel.name)
    wrote = False
    for fname in names:
        if not fname.lower().endswith((".py", ".js", ".mjs", ".cjs", ".json", ".txt", ".md")):
            continue
        child = f"{parent}/{fname}".strip("/")
        if _safe_rel(child) is None:
            continue
        text = _file(snap, child)
        if text is None:
            continue
        dest = root / child
        if not _under(root, dest):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        wrote = True
    script_path = root / rel.as_posix()
    if not wrote or not script_path.is_file():
        shutil.rmtree(root, ignore_errors=True)
        return None
    return script_path


def _write_skill_tree(dest: Path, snap: RepoSnapshot, prefix: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    keys = [k for k in snap.files if k == "SKILL.md" or k.startswith(prefix + "/") or (prefix == "" and "/" not in k)]
    if prefix:
        keys = [k for k in snap.files if k == f"{prefix}/SKILL.md" or k.startswith(prefix + "/")]
    else:
        keys = [k for k in list(snap.files) if "/" not in k or k.startswith("references/")]
    if not any(k.endswith("SKILL.md") for k in keys):
        raise RuntimeError("SKILL.md 없음")
    for key in keys:
        if not key.lower().endswith((".md", ".txt", ".json", ".yml", ".yaml", ".py")):
            continue
        rel = key[len(prefix) + 1 :] if prefix and key.startswith(prefix + "/") else key
        safe = _safe_rel(rel)
        if safe is None:
            continue
        target = dest / safe
        if not _under(dest, target):
            continue
        text = _file(snap, key)
        if text is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _project_store(home: Path) -> bool:
    return (home / "PROJECT").is_file()


def _write_project_mcp(home: Path, name: str, block: dict[str, Any]) -> None:
    path = home / "mcp.json"
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    safe = _safe_name(name)
    if safe in servers and not _same_server(servers.get(safe), block):
        raise RuntimeError("기존 설정과 달라 덮어쓰지 않습니다")
    servers[safe] = block
    data["mcpServers"] = servers
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_server(home: Path, name: str, block: dict[str, Any]) -> None:
    if _project_store(home):
        _write_project_mcp(home, name, block)
        return
    path = home / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _read_config(home)
    servers = data.get("mcp_servers")
    if not isinstance(servers, dict):
        servers = {}
    safe = _safe_name(name)
    if safe in servers and not _same_server(servers.get(safe), block):
        raise RuntimeError("기존 설정과 달라 덮어쓰지 않습니다")
    bak = path.with_name("config.yaml.bak-iris-ext")
    if path.is_file() and not bak.is_file():
        try:
            shutil.copy2(path, bak)
        except OSError:
            pass
    servers[safe] = block
    data["mcp_servers"] = servers
    _dump_config(path, data)


def _same_server(current: Any, block: dict[str, Any]) -> bool:
    if not isinstance(current, dict):
        return False
    if str(current.get("command") or "") != str(block.get("command") or ""):
        return False
    if list(current.get("args") or []) != list(block.get("args") or []):
        return False
    if str(current.get("cwd") or "") != str(block.get("cwd") or ""):
        return False
    return _public_env(current.get("env")) == _public_env(block.get("env"))


def _public_env(env: Any) -> dict[str, str]:
    if not isinstance(env, dict):
        return {}
    return {str(k): str(v) for k, v in env.items() if str(k) not in ("PYTHONUNBUFFERED", "PYTHONIOENCODING")}


def _read_config(home: Path) -> dict[str, Any]:
    path = home / "config.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML 필요") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("config.yaml 형식이 올바르지 않습니다")
    return data


def _dump_config(path: Path, data: dict[str, Any]) -> None:
    import yaml

    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _mcp_specs(snap: RepoSnapshot, secrets: dict[str, str]) -> list[McpSpec] | str:
    manifests = [k for k in snap.files if Path(k).name.lower() in ("mcp.json", ".mcp.json")]
    cursor = [k for k in snap.files if k.replace("\\", "/").lower().endswith(".cursor/mcp.json")]
    claude = [k for k in snap.files if ".claude/" in k.lower() and k.lower().endswith("mcp.json")]
    found: list[McpSpec] = []
    rejected: list[str] = []
    for key in manifests + cursor + claude:
        specs, why = _specs_from_mcp_json(snap.files.get(key) or "", Path(key).stem or "mcp", key)
        found.extend(specs)
        rejected.extend(why)
    if found:
        return _dedupe_specs(found)
    if rejected:
        return "MCP 설정을 찾았지만 실행하지 않았습니다: " + "; ".join(rejected)
    server_json = [k for k in snap.files if Path(k).name.lower() == "server.json"]
    for key in server_json:
        found.extend(_specs_from_server_json(snap.files.get(key) or "", key))
    if found:
        return _dedupe_specs(found)
    packages = [k for k in snap.files if Path(k).name.lower() == "package.json"]
    pkg_specs: list[McpSpec] = []
    for key in packages:
        spec = _spec_from_package(snap.files.get(key) or "", snap, key)
        if spec is not None:
            pkg_specs.append(spec)
    if len(pkg_specs) > 1:
        return "MCP 정의가 여러 개입니다 (" + ", ".join(s.name for s in pkg_specs) + "). 폴더 URL을 지정해주세요."
    if pkg_specs:
        return pkg_specs
    readme = _readme(snap)
    if readme:
        spec = _spec_from_readme(readme)
        if spec is not None:
            return [spec]
        if "```" in readme and re.search(r"\b(bash|sh|powershell|cmd)(\.exe)?\b", readme, re.I):
            return "README에 셸 설치 명령만 있어 실행하지 않았습니다. mcp.json 또는 npx/uvx 한 줄 정의가 필요합니다."
    return []


def _specs_from_mcp_json(text: str, fallback: str, source: str) -> tuple[list[McpSpec], list[str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], ["mcp.json 을 읽지 못했습니다"]
    if not isinstance(data, dict):
        return [], []
    servers = data.get("mcpServers") or data.get("mcp_servers")
    items: list[tuple[str, dict]] = []
    if isinstance(servers, dict):
        items = [(str(k), v) for k, v in servers.items() if isinstance(v, dict)]
    elif data.get("command") or data.get("url"):
        items = [(fallback, data)]
    out: list[McpSpec] = []
    rejected: list[str] = []
    for name, block in items:
        if block.get("url"):
            rejected.append(f"{name}: HTTP MCP는 자동 실행하지 않습니다")
            continue
        spec = _spec_from_block(name, block, source)
        if spec is not None:
            out.append(spec)
            continue
        err = _command_error(str(block.get("command") or ""), [str(a) for a in block.get("args") or []])
        if err:
            rejected.append(f"{name}: {err}")
    return out, rejected


def _specs_from_server_json(text: str, source: str) -> list[McpSpec]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    out: list[McpSpec] = []
    for pkg in data.get("packages") or []:
        if not isinstance(pkg, dict):
            continue
        reg = str(pkg.get("registry_type") or pkg.get("registryType") or "").lower()
        ident = str(pkg.get("identifier") or "").strip()
        transport = pkg.get("transport") if isinstance(pkg.get("transport"), dict) else {}
        if str(transport.get("type") or "stdio") not in ("stdio", ""):
            continue
        if reg == "npm":
            command, args = "npx", ["-y", ident]
        elif reg == "pypi":
            command, args = "uvx", [ident]
        else:
            continue
        missing = []
        for ev in pkg.get("environment_variables") or pkg.get("environmentVariables") or []:
            if isinstance(ev, dict) and ev.get("required") and ev.get("name"):
                missing.append(str(ev["name"]))
        name = _safe_name(str(data.get("name") or ident).split("/")[-1])
        spec = _spec_from_block(name, {"command": command, "args": args, "env": {k: "" for k in missing}}, source)
        if spec is not None:
            out.append(spec)
    return out


def _spec_from_package(text: str, snap: RepoSnapshot, source: str) -> McpSpec | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").strip()
    explicit = data.get("mcp")
    if isinstance(explicit, dict) and (explicit.get("command") or explicit.get("args")):
        return _spec_from_block(name or "mcp", explicit, source)
    readme = _readme(snap)
    blob = f"{name} {data.get('description') or ''} {readme}".lower()
    if not name or "mcp" not in blob and "modelcontextprotocol" not in blob:
        return None
    if not isinstance(data.get("bin"), (str, dict)) and "mcp" not in name.lower() and "modelcontextprotocol" not in name.lower():
        return None
    if readme and name not in readme and "npx" not in readme and "uvx" not in readme:
        return None
    spec = _spec_from_block(name.split("/")[-1], {"command": "npx", "args": ["-y", name]}, source)
    if spec is not None and _readme_requires_dir(readme):
        spec.need_dir = True
    return spec


def _spec_from_readme(text: str) -> McpSpec | None:
    hits: list[tuple[str, list[str], bool]] = []
    for match in re.finditer(r"(?m)(?:^|[\s`])(npx|uvx)\s+(-y\s+)?(\S+)([^\n`]*)", text):
        cmd = match.group(1)
        pkg = match.group(3).strip().strip("`\"'")
        rest = (match.group(4) or "").strip()
        if not _ARG_OK.match(pkg) or ".." in pkg:
            continue
        args = ["-y", pkg] if match.group(2) else [pkg]
        need_dir = False
        for tok in rest.split():
            tok = tok.strip("`\"'")
            if not tok or tok.startswith("#"):
                break
            if tok.startswith("<") or tok.endswith(">"):
                need_dir = True
                continue
            if not _ARG_OK.match(tok) or ".." in tok:
                need_dir = False
                args = []
                break
            args.append(tok)
        if not args:
            continue
        hits.append((cmd, args, need_dir))
    uniq = {(c, tuple(a), d) for c, a, d in hits}
    if len(uniq) != 1:
        return None
    cmd, args, need_dir = hits[0]
    return _spec_from_block(args[-1].split("/")[-1], {"command": cmd, "args": args}, "readme", need_dir=need_dir)


def _readme_requires_dir(readme: str) -> bool:
    text = readme or ""
    if re.search(r"<(?:allowed[-_ ]?)?dir", text, re.IGNORECASE):
        return True
    return bool(
        re.search(r"without command-line arguments", text, re.IGNORECASE)
        and re.search(r"throw an error|will throw", text, re.IGNORECASE)
    )


def _spec_from_block(name: str, block: dict, source: str, need_dir: bool = False) -> McpSpec | None:
    command = str(block.get("command") or "").strip()
    raw_args = block.get("args") if isinstance(block.get("args"), list) else []
    args = [str(a) for a in raw_args]
    err = _command_error(command, args)
    if err:
        return None
    env_in = block.get("env") if isinstance(block.get("env"), dict) else {}
    env: dict[str, str] = {}
    missing: list[str] = []
    for key, val in env_in.items():
        if not _ENV_KEY.match(str(key)):
            continue
        text = "" if val is None else str(val)
        if _PLACEHOLDER.match(text.strip()):
            missing.append(str(key))
        else:
            env[str(key)] = text
    script = _local_script(command, args)
    safe = _safe_name(name)
    if not safe:
        return None
    return McpSpec(safe, command, args, env, missing, script, need_dir, source)


def _command_error(command: str, args: list[str]) -> str:
    base = _cmd_base(command)
    if base not in _ALLOWED_CMDS:
        return f"허용되지 않은 실행 파일 ({base or command})"
    for arg in args:
        if not _ARG_OK.match(arg) or ".." in arg.replace("\\", "/").split("/"):
            return f"안전하지 않은 인자 ({arg})"
    return ""


def _normalize_command(command: str, args: list[str]) -> tuple[str, list[str], str]:
    err = _command_error(command, args)
    if err:
        return "", [], err
    base = _cmd_base(command)
    if base in ("npx", "uvx", "uv", "node"):
        from iris.system.executable_resolve import resolve_executable

        if resolve_executable(base) is None and resolve_executable(command) is None:
            return "", [], f"{base}를 찾을 수 없습니다"
        return base, args, ""
    if base in ("python", "python3", "py"):
        return sys.executable, args, ""
    return "", [], f"허용되지 않은 실행 파일 ({base})"


def _local_script(command: str, args: list[str]) -> str | None:
    if _cmd_base(command) not in ("python", "python3", "py", "node"):
        return None
    scripts = [a for a in args if a.endswith((".py", ".js", ".mjs", ".cjs")) and not a.startswith("-")]
    if len(scripts) != 1:
        return None
    if _safe_rel(scripts[0]) is None:
        return None
    return scripts[0]


def _skill_files(snap: RepoSnapshot) -> list[str]:
    found = [k for k in snap.files if Path(k).name == "SKILL.md"]
    found.sort(key=lambda p: (p.count("/"), p))
    return found


def _skill_name(snap: RepoSnapshot, rel: str) -> str:
    text = _file(snap, rel) or ""
    match = re.search(r"(?m)^name:\s*[\"']?([A-Za-z0-9_-]{1,64})", text)
    if match:
        return _safe_name(match.group(1))
    parent = Path(rel).parent.name
    return _safe_name(parent if parent and parent != "." else "skill")


def _readme(snap: RepoSnapshot) -> str:
    for key, text in snap.files.items():
        if Path(key).name.lower() == "readme.md":
            return text
    return ""


def _dedupe_specs(specs: list[McpSpec]) -> list[McpSpec]:
    seen: set[str] = set()
    out: list[McpSpec] = []
    for spec in specs:
        if spec.name in seen:
            continue
        seen.add(spec.name)
        out.append(spec)
    return out


def _file(snap: RepoSnapshot, rel: str) -> str | None:
    if rel in snap.files:
        return snap.files[rel]
    if snap.read is None:
        return None
    try:
        return snap.read(rel)
    except Exception:
        return None


def _not_extension_message(specs: list[McpSpec] | str) -> str:
    if isinstance(specs, str) and specs:
        return specs
    return (
        "이 저장소에서 MCP/Skill 구성을 찾지 못했습니다. "
        "mcp.json, .mcp.json, server.json, SKILL.md, 또는 npx/uvx 한 줄 정의가 없습니다. "
        "설치하지 않았습니다."
    )


def _first_github_url(text: str) -> str:
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;:)")
        if parse_github_url(url):
            return url
    return ""


def _interesting(name: str) -> bool:
    low = name.lower()
    if low in _MANIFESTS:
        return True
    return low.endswith((".py", ".js", ".mjs", ".md", ".json", ".yml", ".yaml", ".toml", ".txt"))


def _descend(name: str, depth: int) -> bool:
    if name in _SKIP_DIRS:
        return False
    if name.startswith(".") and name not in (".cursor", ".claude"):
        return False
    return depth < 2 or name in (".cursor", ".claude")


def _gh_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "iris-light",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError("저장소를 찾지 못했습니다. 주소가 비공개이거나 잘못되었습니다.") from exc
        if exc.code in (403, 429):
            raise RuntimeError(f"GitHub 요청이 거절되었습니다 (HTTP {exc.code}). 잠시 후 다시 시도해주세요.") from exc
        raise RuntimeError(f"GitHub 응답 오류 HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"GitHub에 연결하지 못했습니다: {exc}") from exc


def _contents_url(owner: str, repo: str, path: str, ref: str) -> str:
    quoted = urllib.parse.quote(path.strip("/"), safe="/")
    base = f"https://api.github.com/repos/{owner}/{repo}/contents"
    if quoted:
        base += f"/{quoted}"
    return base + "?ref=" + urllib.parse.quote(ref)


def _download_file(owner: str, repo: str, path: str, ref: str, timeout: float) -> str:
    data = _gh_json(_contents_url(owner, repo, path, ref), timeout)
    if not isinstance(data, dict):
        raise RuntimeError(f"파일이 아닙니다: {path}")
    return _decode_content(data)


def _decode_content(data: dict) -> str:
    if str(data.get("encoding") or "") == "base64":
        raw = base64.b64decode(str(data.get("content") or ""))
        return raw.decode("utf-8", errors="replace")
    if isinstance(data.get("content"), str):
        return str(data["content"])
    raise RuntimeError("파일 내용을 읽지 못했습니다.")


def _send(proc: subprocess.Popen, msg: dict) -> None:
    assert proc.stdin
    proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
    proc.stdin.flush()


_EOF = object()
_TIMEOUT = object()


def _parse_json_line(raw: bytes) -> dict | None:
    """한 줄에서 JSON-RPC 객체만 꺼낸다. npm 진행 표시(\\r)가 앞에 붙어도 된다."""
    for part in raw.split(b"\r"):
        text = part.strip()
        if not text:
            continue
        candidates = [text]
        brace = text.find(b"{")
        if brace > 0:
            candidates.append(text[brace:])
        for piece in candidates:
            try:
                obj = json.loads(piece.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(obj, dict):
                return obj
    return None


def _read_frame(proc: subprocess.Popen, deadline: float) -> tuple[object, str]:
    """stdout에서 프레임 하나. (dict | _EOF | _TIMEOUT, raw)."""
    assert proc.stdout
    while time_monotonic() < deadline:
        if proc.poll() is not None:
            return _EOF, ""
        line = _readline(proc.stdout, deadline)
        if line is _TIMEOUT:
            return _TIMEOUT, ""
        if line is _EOF:
            return _EOF, ""
        if not isinstance(line, (bytes, bytearray)):
            return _EOF, ""
        raw = bytes(line)
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(b"content-length"):
            try:
                length = int(stripped.split(b":", 1)[1].strip() or b"0")
            except ValueError:
                continue
            while True:
                header = _readline(proc.stdout, deadline)
                if header is _TIMEOUT:
                    return _TIMEOUT, ""
                if header is _EOF:
                    return _EOF, ""
                if header in (b"\r\n", b"\n", b""):
                    break
            body = proc.stdout.read(length)
            shown = (stripped + b"\n" + body)[:500].decode("utf-8", errors="replace")
            try:
                obj = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(obj, dict):
                return obj, shown
            continue
        obj = _parse_json_line(stripped)
        shown = stripped[:500].decode("utf-8", errors="replace")
        if obj is not None:
            return obj, shown
    return _TIMEOUT, ""


def _answer_server_request(proc: subprocess.Popen, msg: dict) -> None:
    """서버가 클라이언트로 보낸 요청. 무시하면 서버가 다음 응답을 멈춘다."""
    method = str(msg.get("method") or "")
    req_id = msg.get("id")
    if method == "roots/list":
        result: dict[str, Any] = {"roots": []}
    elif method == "ping":
        result = {}
    else:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            },
        )
        return
    _send(proc, {"jsonrpc": "2.0", "id": req_id, "result": result})


def _wait_response(
    proc: subprocess.Popen,
    expect_id: int,
    timeout: float,
    *,
    phase: str,
    stderr_chunks: list[str],
    frames: list[str],
) -> tuple[dict | None, str]:
    """id가 맞는 응답까지 알림은 건너뛰고 서버 요청은 답한다."""
    deadline = time_monotonic() + max(0.1, float(timeout))
    while time_monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            return None, _phase_dead(phase, code, stderr_chunks)
        msg, raw = _read_frame(proc, deadline)
        if raw:
            frames.append(raw[:500])
            del frames[:-12]
        if msg is _TIMEOUT:
            break
        if msg is _EOF:
            code = proc.poll()
            if code is None:
                err = _stderr_text(stderr_chunks)
                text = f"{phase}: stdout이 닫혔습니다"
                return None, f"{text}: {err[:240]}" if err else text
            return None, _phase_dead(phase, code, stderr_chunks)
        if not isinstance(msg, dict):
            continue
        method = msg.get("method")
        if method and "id" not in msg:
            frames.append(f"notification {method}")
            del frames[:-12]
            continue
        if method and "id" in msg:
            frames.append(f"server-request {method}")
            del frames[:-12]
            _answer_server_request(proc, msg)
            continue
        if msg.get("id") == expect_id:
            return msg, ""
    code = proc.poll()
    if code is not None:
        return None, _phase_dead(phase, code, stderr_chunks)
    err = _stderr_text(stderr_chunks)
    text = f"{phase}: 응답 시간이 초과되었습니다 ({timeout:.0f}s)"
    return None, f"{text}: {err[:240]}" if err else text


def _stderr_text(chunks: list[str]) -> str:
    return "".join(chunks).strip()


def _phase_dead(phase: str, code: int, stderr_chunks: list[str]) -> str:
    err = _stderr_text(stderr_chunks)
    text = f"{phase}: 프로세스가 종료되었습니다 (code {code})"
    return f"{text}: {err[:240]}" if err else text


def _readline(stdout, deadline: float) -> object:
    box: queue.Queue = queue.Queue(1)

    def _read() -> None:
        try:
            box.put(stdout.readline())
        except Exception as exc:  # noqa: BLE001
            box.put(exc)

    threading.Thread(target=_read, daemon=True).start()
    remain = deadline - time_monotonic()
    if remain <= 0:
        return _TIMEOUT
    try:
        item = box.get(timeout=remain)
    except queue.Empty:
        return _TIMEOUT
    if isinstance(item, Exception):
        return _EOF
    if not item:
        return _EOF
    return item


def time_monotonic() -> float:
    import time

    return time.monotonic()


def _callable_tool(tools: list) -> str:
    for tool in tools:
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        name = str(tool.get("name"))
        if name in {"get-env", "env"}:
            continue
        schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        if not required:
            return name
    return ""


def _call_text(msg: dict | None) -> str | None:
    if not isinstance(msg, dict) or "result" not in msg:
        return None
    result = msg.get("result")
    if isinstance(result, dict) and result.get("isError"):
        return None
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        bits = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                bits.append(str(item["text"]))
        if bits:
            return " ".join(bits)
    return "ok"


def _call_preview(msg: dict | None) -> str | None:
    text = _call_text(msg)
    if text is None:
        return None
    return text[:180]


def _fail_detail(
    proc: subprocess.Popen,
    msg: dict | None,
    stderr_chunks: list[str],
    secrets: dict[str, str],
    *,
    phase: str = "mcp",
) -> str:
    if isinstance(msg, dict) and msg.get("error"):
        text = f"{phase}: {msg.get('error')}"
    elif proc.poll() not in (None, 0):
        text = f"{phase}: 프로세스가 종료되었습니다 (code {proc.poll()})"
    else:
        text = f"{phase}: 응답이 없습니다"
    err = _stderr_text(stderr_chunks)
    if err:
        text = f"{text}: {err[:240]}"
    return _redact(text, secrets)[:300]


def _kill_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            from iris.system.win_subprocess import no_window_kwargs

            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **no_window_kwargs(),
            )
        except Exception:
            proc.kill()
    else:
        proc.kill()
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _discard_sources(home: Path, name: str) -> None:
    shutil.rmtree(home / "mcp-sources" / _safe_name(name), ignore_errors=True)


def _under(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _safe_rel(rel: str) -> Path | None:
    if rel is None:
        return None
    text = rel.replace("\\", "/").strip("/")
    if not text:
        return Path()
    parts = text.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    if any(not _SAFE_PART.match(p) for p in parts):
        return None
    return Path(*parts)


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^\w\-]+", "-", (name or "").strip(), flags=re.UNICODE).strip("-_").lower()
    return safe[:64]


def _cmd_base(command: str) -> str:
    name = Path(command).name.lower()
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def _clean_secret(val: str) -> str:
    text = (val or "").replace("\x00", "").replace("\r", "").replace("\n", "").strip()
    if not text or len(text) > 512:
        return ""
    return text


def _accepted_secrets(secrets: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in secrets.items():
        if _ENV_KEY.match(str(key)):
            clean = _clean_secret(str(val))
            if clean:
                out[str(key)] = clean
    return out


def _redact(text: str, secrets: dict[str, str]) -> str:
    out = text or ""
    for val in secrets.values():
        if val and len(val) >= 4:
            out = out.replace(val, "***")
    return out
