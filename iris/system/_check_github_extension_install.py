"""GitHub MCP/Skill 설치 실행 경로 검증.

python -m iris.system._check_github_extension_install
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from iris.system.github_extension_install import (
    ExtensionRequest,
    RepoSnapshot,
    install_from_request,
    load_state,
    parse_extension_request,
    parse_github_url,
    probe_mcp,
)

_SERVER = r"""
import json, sys

def read_msg():
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    if line.lower().startswith(b"content-length"):
        length = int(line.split(b":", 1)[1].strip() or b"0")
        while True:
            header = sys.stdin.buffer.readline()
            if header in (b"\r\n", b"\n", b""):
                break
        return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))
    raw = line.strip()
    if not raw:
        return read_msg()
    return json.loads(raw.decode("utf-8"))

def write_msg(msg):
    sys.stdout.buffer.write((json.dumps(msg) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

while True:
    msg = read_msg()
    if not msg:
        break
    if msg.get("id") is None:
        continue
    method = msg.get("method")
    i = msg["id"]
    if method == "initialize":
        write_msg({"jsonrpc": "2.0", "id": i, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fixture", "version": "0"},
        }})
    elif method == "tools/list":
        write_msg({"jsonrpc": "2.0", "id": i, "result": {"tools": [{
            "name": "ping",
            "description": "pong",
            "inputSchema": {"type": "object", "properties": {}},
        }]}})
    elif method == "tools/call":
        write_msg({"jsonrpc": "2.0", "id": i, "result": {
            "content": [{"type": "text", "text": "pong"}],
        }})
    else:
        write_msg({"jsonrpc": "2.0", "id": i, "result": {}})
"""

_SKILL = """---
name: demo-skill
description: fixture skill for IRIS install checks
---

# demo-skill

Say hello from the fixture skill.
"""

_MCP_JSON = """{
  "mcpServers": {
    "fixture-mcp": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
"""


def _snap(files: dict[str, str]) -> RepoSnapshot:
    return RepoSnapshot(label="example/fixture", files=dict(files))


def _fetch(files: dict[str, str]):
    def fetch(_url: str) -> RepoSnapshot:
        return _snap(files)

    return fetch


def _check_parse() -> None:
    mcp = parse_extension_request("https://github.com/example/example-mcp 이 MCP 연결해줘")
    assert mcp and mcp.kind == "mcp", mcp
    skill = parse_extension_request("https://github.com/example/my-skill 이 Skill 적용해줘")
    assert skill and skill.kind == "skill", skill
    auto = parse_extension_request(
        "https://github.com/example/repo 이거 IRIS에서 사용할 수 있게 추가해줘"
    )
    assert auto and auto.kind == "auto", auto
    assert parse_extension_request("https://github.com/foo/bar 이 함수 추가해줘") is None
    assert parse_github_url("https://github.com/o/r/tree/main/src/filesystem") == (
        "o",
        "r",
        "main",
        "src/filesystem",
    )
    assert parse_github_url("https://github.com/o/r/issues/1") is None


def _check_mcp(home: Path) -> None:
    req = ExtensionRequest("https://github.com/example/fixture-mcp", "mcp")
    result = install_from_request(
        req,
        home=home,
        fetch=_fetch({"mcp.json": _MCP_JSON, "server.py": _SERVER}),
    )
    assert result.status == "installed", result.message
    assert result.tools == ["ping"], result.tools
    assert result.called_tool == "ping", result.called_tool
    assert "pong" in result.call_preview, result.call_preview
    assert (home / "config.yaml").is_file()
    state = load_state(home)
    assert "fixture-mcp" in state["mcp"], state


def _check_skill(home: Path) -> None:
    req = ExtensionRequest("https://github.com/example/my-skill", "skill")
    result = install_from_request(req, home=home, fetch=_fetch({"SKILL.md": _SKILL}))
    assert result.status == "installed", result.message
    path = home / "skills" / "custom" / "demo-skill" / "SKILL.md"
    assert path.is_file(), path
    assert "demo-skill" in path.read_text(encoding="utf-8")
    assert "demo-skill" in load_state(home)["skills"]


def _check_duplicate(home: Path) -> None:
    req = ExtensionRequest("https://github.com/example/fixture-mcp", "mcp")
    fetch = _fetch({"mcp.json": _MCP_JSON, "server.py": _SERVER})
    again = install_from_request(req, home=home, fetch=fetch)
    assert again.status == "already", again.message
    assert "이미" in again.message
    assert load_state(home)["mcp"].count("fixture-mcp") == 1
    skill = install_from_request(
        ExtensionRequest("https://github.com/example/my-skill", "skill"),
        home=home,
        fetch=_fetch({"SKILL.md": _SKILL}),
    )
    assert skill.status == "already", skill.message


def _check_conflict(home: Path) -> None:
    other = """{
      "mcpServers": {
        "fixture-mcp": {"command": "npx", "args": ["-y", "@example/other-mcp"]}
      }
    }"""
    before = (home / "config.yaml").read_text(encoding="utf-8")
    result = install_from_request(
        ExtensionRequest("https://github.com/example/fixture-mcp", "mcp"),
        home=home,
        fetch=_fetch({"mcp.json": other}),
    )
    assert result.status == "failed", result.message
    assert "덮어쓰지 않았" in result.message
    assert (home / "config.yaml").read_text(encoding="utf-8") == before


def _check_bad_repo(home: Path) -> None:
    result = install_from_request(
        ExtensionRequest("https://github.com/example/plain", "auto"),
        home=home,
        fetch=_fetch({"README.md": "# hello\n\njust a readme\n"}),
    )
    assert result.status == "refused", result.message
    assert "찾지 못했습니다" in result.message
    assert load_state(home)["mcp"] == []
    assert not (home / "skills" / "custom").exists()


def _check_injection(home: Path) -> None:
    sentinel = home / "sentinel-should-not-exist.txt"
    evil = """{
      "mcpServers": {
        "evil": {"command": "powershell", "args": ["-Command", "Set-Content"]}
      }
    }"""
    result = install_from_request(
        ExtensionRequest("https://github.com/example/evil", "mcp"),
        home=home,
        fetch=_fetch({"mcp.json": evil}),
    )
    assert result.status == "refused", result.message
    assert "허용되지 않은" in result.message, result.message
    assert not sentinel.exists()
    assert "evil" not in load_state(home)["mcp"]
    bad_arg = """{
      "mcpServers": {
        "evil2": {"command": "python", "args": ["server.py;calc"]}
      }
    }"""
    result2 = install_from_request(
        ExtensionRequest("https://github.com/example/evil2", "mcp"),
        home=home,
        fetch=_fetch({"mcp.json": bad_arg, "server.py": _SERVER}),
    )
    assert result2.status == "refused", result2.message
    assert "안전하지 않은" in result2.message, result2.message


def _check_secret(home: Path) -> None:
    token = "super-secret-token-value"
    raw = """{
      "mcpServers": {
        "token-mcp": {
          "command": "python",
          "args": ["server.py"],
          "env": {"GITHUB_TOKEN": ""}
        }
      }
    }"""
    files = {"mcp.json": raw, "server.py": _SERVER}
    first = install_from_request(
        ExtensionRequest("https://github.com/example/token-mcp", "mcp"),
        home=home,
        fetch=_fetch(files),
    )
    assert first.status == "needs_input", first.message
    assert "GITHUB_TOKEN" in first.message
    assert token not in first.message
    assert "token-mcp" not in load_state(home)["mcp"]
    second = install_from_request(
        ExtensionRequest("https://github.com/example/token-mcp", "mcp"),
        home=home,
        secrets={"GITHUB_TOKEN": token},
        fetch=_fetch(files),
    )
    assert second.status == "installed", second.message
    assert token not in second.message
    saved = (home / "config.yaml").read_text(encoding="utf-8")
    assert token in saved
    assert "pong" in second.call_preview


def _check_persist(home: Path) -> None:
    state = load_state(home)
    assert "fixture-mcp" in state["mcp"], state
    assert "demo-skill" in state["skills"], state
    import yaml

    data = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    block = data["mcp_servers"]["fixture-mcp"]
    probe = probe_mcp(
        str(block["command"]),
        list(block["args"]),
        block.get("env") or {},
        cwd=str(block.get("cwd") or ""),
        timeout=15,
    )
    assert probe["ok"], probe
    assert probe["tools"] == ["ping"]
    assert probe["call_preview"] == "pong"


def _check_need_dir(home: Path) -> None:
    readme = "npx -y @example/demo-mcp <allowed-directory>\n"
    result = install_from_request(
        ExtensionRequest("https://github.com/example/demo-mcp", "mcp"),
        home=home,
        fetch=_fetch({"README.md": readme}),
    )
    assert result.status == "needs_input", result.message
    assert result.need_dir, result.message
    assert "demo-mcp" not in load_state(home)["mcp"]
    pkg = """{
      "name": "@modelcontextprotocol/server-filesystem",
      "bin": {"mcp-server-filesystem": "dist/index.js"},
      "description": "MCP server for filesystem"
    }"""
    noted = (
        "Published as `@modelcontextprotocol/server-filesystem`.\n"
        "If server starts without command-line arguments AND client doesn't support roots, "
        "the server will throw an error during initialization.\n"
    )
    asked = install_from_request(
        ExtensionRequest("https://github.com/example/filesystem", "mcp"),
        home=home,
        fetch=_fetch({"package.json": pkg, "README.md": noted}),
    )
    assert asked.status == "needs_input", asked.message
    assert asked.need_dir, asked.message
    assert "server-filesystem" not in load_state(home)["mcp"]


def _check_live() -> None:
    from iris.system.github_extension_install import _mcp_specs, fetch_github

    try:
        skill_home = Path(tempfile.mkdtemp(prefix="iris-ext-live-"))
        live = install_from_request(
            ExtensionRequest(
                "https://github.com/anthropics/skills/tree/main/skills/skill-creator",
                "skill",
            ),
            home=skill_home,
        )
    except Exception as exc:  # noqa: BLE001
        print("live skill skip", exc)
        if "skill_home" in locals():
            shutil.rmtree(skill_home, ignore_errors=True)
        return
    if live.status != "installed":
        print("live skill skip", live.status, live.message[:200])
        shutil.rmtree(skill_home, ignore_errors=True)
        return
    assert live.skill_paths, live.message
    assert Path(live.skill_paths[0]).is_file()
    print("live skill", live.skill_names)
    shutil.rmtree(skill_home, ignore_errors=True)
    try:
        snap = fetch_github(
            "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem"
        )
        specs = _mcp_specs(snap, {})
    except Exception as exc:  # noqa: BLE001
        print("live mcp classify skip", exc)
        return
    print("live mcp classify", specs if isinstance(specs, str) else [(s.name, s.command, s.args, s.need_dir) for s in specs])


def _check_hermes_sees_it(home: Path) -> None:
    from iris.system.iris_agent_gateway import hermes_executable
    from iris.system.github_extension_install import hermes_home

    exe = hermes_executable("hermes")
    if not exe:
        print("hermes mcp test skip: hermes executable missing")
        return
    real = hermes_home() / "config.yaml"
    before = real.stat().st_mtime_ns if real.is_file() else None
    import subprocess

    from iris.system.win_subprocess import no_window_kwargs

    env = os.environ.copy()
    env["HERMES_HOME"] = str(home)
    try:
        proc = subprocess.run(
            [exe, "mcp", "test", "fixture-mcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            env=env,
            check=False,
            **no_window_kwargs(),
        )
    except Exception as exc:  # noqa: BLE001
        print("hermes mcp test skip", exc)
        return
    after = real.stat().st_mtime_ns if real.is_file() else None
    assert before == after, "hermes mcp test touched the real Hermes config"
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0 or "ping" not in out:
        raise SystemExit(f"hermes mcp test failed\n{out[-800:]}")
    print("hermes mcp test ok", "ping" in out)


def _check_skip_notification() -> None:
    """initialize 직후 list_changed 알림이 와도 tools/list 응답을 읽는다."""
    import sys
    import textwrap

    script = Path(tempfile.mkdtemp(prefix="iris-mcp-note-")) / "note_server.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, sys

            def read_msg():
                line = sys.stdin.buffer.readline()
                if not line:
                    return None
                return json.loads(line.decode())

            def write_msg(msg):
                sys.stdout.buffer.write((json.dumps(msg) + "\\n").encode())
                sys.stdout.buffer.flush()

            while True:
                msg = read_msg()
                if not msg:
                    break
                if msg.get("id") is None:
                    continue
                method = msg.get("method")
                i = msg["id"]
                if method == "initialize":
                    write_msg({"jsonrpc": "2.0", "id": i, "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "note", "version": "0"},
                    }})
                    write_msg({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
                elif method == "tools/list":
                    write_msg({"jsonrpc": "2.0", "id": i, "result": {"tools": [{
                        "name": "ping",
                        "inputSchema": {"type": "object", "properties": {}},
                    }]}})
                elif method == "tools/call":
                    write_msg({"jsonrpc": "2.0", "id": i, "result": {
                        "content": [{"type": "text", "text": "pong"}],
                    }})
            """
        ),
        encoding="utf-8",
    )
    result = probe_mcp(sys.executable, ["-u", str(script)], {}, timeout=15)
    assert result["ok"], result
    assert result["tools"] == ["ping"], result
    assert any("notifications/tools/list_changed" in str(frame) for frame in result["frames"]), result["frames"]
    print("notification skip ok")


def _check_npx_spawn_resolves_cmd() -> None:
    """bare npx 는 CreateProcess WinError 2. spawn argv[0] 는 npx.cmd 절대경로."""
    import sys
    from unittest.mock import patch

    from iris.system.executable_resolve import resolve_executable

    resolved = resolve_executable("npx")
    if not resolved:
        print("npx resolve skip: npx not installed")
        return
    captured: dict = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["cwd"] = kwargs.get("cwd")
        captured["shell"] = kwargs.get("shell", False)
        raise OSError("stop-before-stdio")

    allowed = r"C:\Users\serin\Github\Project-IRIS-Light"
    with patch("iris.system.github_extension_install.subprocess.Popen", side_effect=fake_popen):
        result = probe_mcp(
            "npx",
            ["-y", "@modelcontextprotocol/server-filesystem", allowed],
            {},
            cwd="",
        )
    assert result["ok"] is False
    assert captured["shell"] is False
    assert captured["cwd"] is None
    argv = captured["argv"]
    assert Path(argv[0]).is_file(), argv[0]
    assert argv[1:] == ["-y", "@modelcontextprotocol/server-filesystem", allowed]
    if sys.platform == "win32":
        assert argv[0].lower().endswith("npx.cmd"), argv[0]
        assert argv[0] != "npx"
    # PATH에서 nodejs를 빼도 설치 경로로 찾는다.
    if sys.platform == "win32":
        import os

        saved = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = os.pathsep.join(
                p for p in saved.split(os.pathsep) if "nodejs" not in p.lower() and "npm" not in p.lower()
            )
            off_path = resolve_executable("npx")
        finally:
            os.environ["PATH"] = saved
        assert off_path and Path(off_path).is_file(), off_path
        assert off_path.lower().endswith("npx.cmd")
    print("npx spawn resolves", argv[0])


def main() -> None:
    _check_skip_notification()
    _check_npx_spawn_resolves_cmd()
    _check_parse()
    with tempfile.TemporaryDirectory(prefix="iris-ext-") as tmp:
        home = Path(tmp)
        _check_bad_repo(home)
        _check_injection(home)
        _check_need_dir(home)
        _check_mcp(home)
        _check_skill(home)
        _check_duplicate(home)
        _check_conflict(home)
        _check_secret(home)
        _check_persist(home)
        _check_hermes_sees_it(home)
    _check_live()
    print("github extension install ok")


if __name__ == "__main__":
    main()
