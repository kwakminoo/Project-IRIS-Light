"""Hermes에 Iris Control MCP + 스킬을 자동 설치·검증.

Iris 재시작과 무관하게 Hermes config.yaml / skills 폴더에 남겨 둔다.
ponytail: PyYAML로 mcp_servers만 upsert. 최초 변경 전 config.yaml.bak-iris 1회.
천장: 게이트웨이 이미 떠 있으면 MCP 반영을 위해 --replace 재기동.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SKILL_NAMES = (
    "iris-work-start",
    "iris-work-end",
    "iris-session-status",
    "iris-vibe-code",
    "iris-emulator",
    "iris-mobile-mcp",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def hermes_home() -> Path:
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def hermes_config_path() -> Path:
    return hermes_home() / "config.yaml"


def hermes_skills_iris_control_dir() -> Path:
    return hermes_home() / "skills" / "iris-control"


def repo_skills_iris_control_dir() -> Path:
    return project_root() / "integrations" / "hermes-skills" / "iris-control"


def iris_state_dir() -> Path:
    d = Path.home() / ".iris-light"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sync_state_path() -> Path:
    return iris_state_dir() / "hermes_iris_control_sync.json"


@dataclass
class SyncReport:
    ok: bool = True
    config_path: str = ""
    mcp_installed: bool = False
    mcp_changed: bool = False
    mobile_mcp_installed: bool = False
    mobile_mcp_changed: bool = False
    skills_copied: list[str] = field(default_factory=list)
    skills_ok: list[str] = field(default_factory=list)
    skills_missing: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    needs_gateway_reload: bool = False
    # 설정에 등록된 모든 MCP 점검 결과
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    mcp_ok_count: int = 0
    mcp_fail_count: int = 0

    def summary_line(self) -> str:
        if self.errors and not self.mcp_installed:
            return f"Iris↔Hermes control sync fail: {self.errors[0][:100]}"
        bits = []
        if self.mcp_installed:
            bits.append("MCP iris-control ok" + (" (updated)" if self.mcp_changed else ""))
        else:
            bits.append("MCP iris-control missing")
        if self.mobile_mcp_installed:
            bits.append("MCP mobile-mcp ok" + (" (updated)" if self.mobile_mcp_changed else ""))
        else:
            bits.append("MCP mobile-mcp missing")
        bits.append(f"skills {len(self.skills_ok)}/{len(SKILL_NAMES)}")
        if self.mcp_servers:
            bits.append(f"mcp {self.mcp_ok_count}/{len(self.mcp_servers)} healthy")
        return "Iris↔Hermes: " + ", ".join(bits)


def _python_cmd(repo: Path) -> str:
    # Prefer Iris project venv so Hermes always spawns the same interpreter.
    win = repo / ".venv" / "Scripts" / "python.exe"
    unix = repo / ".venv" / "bin" / "python"
    if win.is_file():
        return str(win.resolve())
    if unix.is_file():
        return str(unix.resolve())
    return sys.executable or "py"


def desired_mcp_block(repo: Path) -> dict[str, Any]:
    root = repo.resolve()
    entry = (root / "integrations" / "hermes-mcp" / "iris_control_stdio_entry.py").resolve()
    # Absolute entry script — Hermes does not pass mcp cwd to StdioServerParameters.
    # -u: unbuffered stdout (Hermes MCP SDK handshake times out if Python buffers stdio)
    return {
        "command": _python_cmd(root),
        "args": ["-u", str(entry)],
        "env": {
            "PYTHONUNBUFFERED": "1",
        },
        "timeout": 120,
        "connect_timeout": 60,
        "enabled": True,
    }


def desired_mobile_mcp_block() -> dict[str, Any]:
    """Hermes MCP: @mobilenext/mobile-mcp — same SDK root as Iris android_emulator."""
    from iris.system.android_emulator import _sdk_root

    sdk = str(_sdk_root().resolve())
    platform_tools = str((_sdk_root() / "platform-tools").resolve())
    sep = ";" if sys.platform == "win32" else ":"
    old_path = os.environ.get("PATH", "")
    path = f"{platform_tools}{sep}{old_path}" if old_path else platform_tools
    return {
        "command": "npx",
        "args": ["-y", "@mobilenext/mobile-mcp@latest"],
        "env": {
            "ANDROID_HOME": sdk,
            "ANDROID_SDK_ROOT": sdk,
            "PATH": path,
        },
        "timeout": 120,
        "connect_timeout": 60,
        "enabled": True,
    }


def _mcp_equivalent(a: Any, b: Any) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    for key in ("command", "args", "timeout", "connect_timeout"):
        if a.get(key) != b.get(key):
            return False
    # enabled: missing == True
    if bool(a.get("enabled", True)) != bool(b.get("enabled", True)):
        return False
    a_env = a.get("env") if isinstance(a.get("env"), dict) else {}
    b_env = b.get("env") if isinstance(b.get("env"), dict) else {}
    # ignore empty env noise
    a_filt = {k: v for k, v in a_env.items() if v not in (None, "")}
    b_filt = {k: v for k, v in b_env.items() if v not in (None, "")}
    return a_filt == b_filt


def ensure_mcp_in_config(repo: Path | None = None) -> tuple[bool, bool, str]:
    """Upsert iris-control + mobile-mcp. Returns (iris_installed, any_changed, message)."""
    try:
        import yaml
    except ImportError:
        return (
            False,
            False,
            "PyYAML 패키지(모듈) 없음 — `.venv`에서 `pip install PyYAML` 후 다시 시도",
        )

    repo = repo or project_root()
    path = hermes_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    desired_iris = desired_mcp_block(repo)
    desired_mobile = desired_mobile_mcp_block()

    if path.is_file():
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = yaml.safe_load(raw) or {}
        except Exception as exc:  # noqa: BLE001
            return False, False, f"config.yaml parse error: {exc}"
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}

    servers = data.get("mcp_servers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcp_servers"] = servers

    iris_same = _mcp_equivalent(servers.get("iris-control"), desired_iris)
    mobile_same = _mcp_equivalent(servers.get("mobile-mcp"), desired_mobile)
    if iris_same and mobile_same:
        msg = "mcp iris-control + mobile-mcp already installed"
        if not shutil.which("npx"):
            msg += "; warning: npx not found (Node 20+ required for mobile-mcp)"
        return True, False, msg

    bak = path.with_name("config.yaml.bak-iris")
    if path.is_file() and not bak.is_file():
        try:
            shutil.copy2(path, bak)
        except OSError:
            pass

    updated: list[str] = []
    if not iris_same:
        servers["iris-control"] = desired_iris
        updated.append("iris-control")
    if not mobile_same:
        servers["mobile-mcp"] = desired_mobile
        updated.append("mobile-mcp")
    data["mcp_servers"] = servers
    try:
        path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    except OSError as exc:
        return False, False, f"config.yaml write failed: {exc}"
    msg = "mcp installed/updated: " + ", ".join(updated)
    if not shutil.which("npx"):
        msg += "; warning: npx not found (Node 20+ required for mobile-mcp)"
    return True, True, msg


def ensure_skills_installed(repo: Path | None = None) -> tuple[list[str], list[str], list[str]]:
    """Returns (copied, ok, missing)."""
    repo = repo or project_root()
    src_root = repo / "integrations" / "hermes-skills" / "iris-control"
    dst_root = hermes_skills_iris_control_dir()
    copied: list[str] = []
    ok: list[str] = []
    missing: list[str] = []

    if not src_root.is_dir():
        return [], [], list(SKILL_NAMES)

    dst_root.mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        src = src_root / name
        dst = dst_root / name
        skill_md = src / "SKILL.md"
        if not skill_md.is_file():
            missing.append(name)
            continue
        need = True
        dst_md = dst / "SKILL.md"
        if dst_md.is_file():
            try:
                if dst_md.read_bytes() == skill_md.read_bytes():
                    need = False
            except OSError:
                need = True
        if need:
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
            copied.append(name)
        ok.append(name)
    return copied, ok, missing


def load_mcp_servers_config() -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return {}
    path = hermes_config_path()
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    except Exception:
        return {}
    servers = data.get("mcp_servers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else {}


def _resolve_command(command: str) -> str | None:
    raw = (command or "").strip().strip('"')
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return str(p.resolve())
    found = shutil.which(raw)
    return found


def _probe_iris_control_http() -> tuple[bool, str]:
    """Iris Control Surface가 떠 있으면 live OK."""
    host = "127.0.0.1"
    port = "8765"
    token = ""
    state = Path.home() / ".iris-light"
    try:
        if (state / "control_host").is_file():
            host = (state / "control_host").read_text(encoding="utf-8").strip() or host
        if (state / "control_port").is_file():
            port = (state / "control_port").read_text(encoding="utf-8").strip() or port
        if (state / "control_token").is_file():
            token = (state / "control_token").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    if not token:
        return False, "control_token missing (Iris not ready?)"
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        # /v1/ping 은 UI invoker 없이 응답 — /v1/state 프로브는 UI 스레드 동기화와 데드락
        f"http://{host}:{port}/v1/ping",
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if 200 <= int(resp.status) < 300:
                return True, "control surface reachable"
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"unreachable: {exc}"


def probe_mcp_server(name: str, cfg: Any) -> dict[str, Any]:
    """설정에 등록된 단일 MCP 서버 사전 점검 (프로세스 장기 기동 없음)."""
    out: dict[str, Any] = {
        "name": name,
        "ok": False,
        "enabled": True,
        "kind": "unknown",
        "detail": "",
    }
    if not isinstance(cfg, dict):
        out["detail"] = "invalid config (not a mapping)"
        return out
    if cfg.get("enabled") is False:
        out["enabled"] = False
        out["ok"] = True
        out["kind"] = "disabled"
        out["detail"] = "disabled in config"
        return out

    url = str(cfg.get("url") or "").strip()
    command = str(cfg.get("command") or "").strip()
    if url:
        out["kind"] = "http"
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(url, method="GET")
            headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}
            for hk, hv in headers.items():
                req.add_header(str(hk), str(hv))
            with urllib.request.urlopen(req, timeout=float(cfg.get("connect_timeout") or 5)) as resp:
                out["ok"] = True
                out["detail"] = f"HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            # 401/404 등도 서버가 응답하면 연결은 됨
            if int(exc.code) < 500:
                out["ok"] = True
                out["detail"] = f"HTTP {exc.code} (reachable)"
            else:
                out["detail"] = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            out["detail"] = f"http error: {exc}"
        return out

    if command:
        out["kind"] = "stdio"
        resolved = _resolve_command(command)
        if not resolved:
            out["detail"] = f"command not found: {command}"
            return out
        cwd = str(cfg.get("cwd") or "").strip()
        if cwd:
            try:
                if not Path(cwd).expanduser().is_dir():
                    out["detail"] = f"cwd missing: {cwd}"
                    return out
            except OSError:
                out["detail"] = f"cwd invalid: {cwd}"
                return out
        # iris-control: 바이너리 + (가능하면) Control Surface live
        if name == "iris-control":
            live_ok, live_detail = _probe_iris_control_http()
            out["ok"] = True  # 커맨드/cwd OK — Iris 꺼져 있으면 live만 경고
            out["detail"] = f"command ok; live: {live_detail}"
            if not live_ok:
                out["detail"] = f"command ok but Iris control not live ({live_detail})"
            return out
        out["ok"] = True
        out["detail"] = f"command ok ({Path(resolved).name})"
        return out

    out["detail"] = "no command/url in config"
    return out


def audit_all_mcp_servers() -> list[dict[str, Any]]:
    servers = load_mcp_servers_config()
    return [probe_mcp_server(str(name), cfg) for name, cfg in servers.items()]


def verify_install(repo: Path | None = None) -> SyncReport:
    try:
        import yaml
    except ImportError:
        report = SyncReport(config_path=str(hermes_config_path()), ok=False)
        report.errors.append(
            "PyYAML 패키지(모듈) 없음 — `.venv`에서 `pip install PyYAML` 후 다시 시도"
        )
        return report

    repo = repo or project_root()
    report = SyncReport(config_path=str(hermes_config_path()))
    path = hermes_config_path()
    if not path.is_file():
        report.ok = False
        report.errors.append("Hermes config.yaml missing")
        return report
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    except Exception as exc:  # noqa: BLE001
        report.ok = False
        report.errors.append(f"config parse: {exc}")
        return report
    servers = data.get("mcp_servers") if isinstance(data, dict) else None
    block = servers.get("iris-control") if isinstance(servers, dict) else None
    report.mcp_installed = _mcp_equivalent(block, desired_mcp_block(repo))
    if not report.mcp_installed:
        report.ok = False
        report.errors.append("mcp iris-control not present or stale")
    mobile_block = servers.get("mobile-mcp") if isinstance(servers, dict) else None
    report.mobile_mcp_installed = _mcp_equivalent(mobile_block, desired_mobile_mcp_block())
    if not report.mobile_mcp_installed:
        report.ok = False
        report.errors.append("mcp mobile-mcp not present or stale")
    if not shutil.which("npx"):
        report.messages.append(
            "npx not found - install Node 20+ so Hermes can spawn mobile-mcp"
        )

    dst = hermes_skills_iris_control_dir()
    for name in SKILL_NAMES:
        if (dst / name / "SKILL.md").is_file():
            report.skills_ok.append(name)
        else:
            report.skills_missing.append(name)
            report.ok = False
    if report.skills_missing:
        report.errors.append("skills missing: " + ", ".join(report.skills_missing))
    return report


def sync_iris_control(
    *,
    repo: Path | None = None,
    reconnect_gateway: bool = False,
) -> SyncReport:
    """MCP + 스킬 설치 후 검증. Hermes 디스크에 남겨 Iris 재시작에도 유지.

    - iris-control upsert (이미 동일하면 유지)
    - 등록된 모든 mcp_servers 사전 점검
    - reconnect_gateway=True 이면 gateway가 MCP를 다시 붙이도록 표시
    """
    repo = repo or project_root()
    report = SyncReport(config_path=str(hermes_config_path()))

    try:
        installed, changed, msg = ensure_mcp_in_config(repo)
        report.mcp_installed = installed
        report.mcp_changed = changed
        report.messages.append(msg)
        if "mobile-mcp" in msg and ("updated" in msg or "installed/updated" in msg):
            report.mobile_mcp_changed = True
        if not installed:
            report.ok = False
            report.errors.append(msg)
        if changed:
            report.needs_gateway_reload = True
        # npx 없으면 probe/audit가 잡음 — config upsert는 유지 (Node 설치 후 바로 동작)
    except Exception as exc:  # noqa: BLE001
        report.ok = False
        report.errors.append(f"mcp sync: {exc}")

    try:
        copied, ok, missing = ensure_skills_installed(repo)
        report.skills_copied = copied
        report.skills_ok = ok
        report.skills_missing = missing
        if copied:
            report.messages.append("skills copied: " + ", ".join(copied))
            report.needs_gateway_reload = True
        if missing:
            report.ok = False
            report.errors.append("skills missing in repo: " + ", ".join(missing))
    except Exception as exc:  # noqa: BLE001
        report.ok = False
        report.errors.append(f"skills sync: {exc}")

    try:
        from iris.system.hermes_memory_nudge import ensure_memory_nudge

        nudge = ensure_memory_nudge()
        report.messages.append(nudge)
        if "updated" in nudge:
            report.needs_gateway_reload = True
    except Exception as exc:  # noqa: BLE001
        report.messages.append(f"memory nudge skip: {exc}")

    verified = verify_install(repo)
    if not verified.ok:
        report.ok = False
        for e in verified.errors:
            if e not in report.errors:
                report.errors.append(e)
    report.mcp_installed = verified.mcp_installed
    report.mobile_mcp_installed = verified.mobile_mcp_installed
    report.skills_ok = verified.skills_ok
    report.skills_missing = verified.skills_missing
    for m in verified.messages:
        if m not in report.messages:
            report.messages.append(m)

    # 등록된 모든 MCP 점검 (다른 서버 설정은 건드리지 않고 상태만 확인·기록)
    try:
        audited = audit_all_mcp_servers()
        report.mcp_servers = audited
        report.mcp_ok_count = sum(1 for s in audited if s.get("ok"))
        report.mcp_fail_count = sum(
            1 for s in audited if s.get("enabled", True) and not s.get("ok")
        )
        if audited:
            report.messages.append(
                f"mcp audit: {report.mcp_ok_count}/{len(audited)} ok"
            )
        for s in audited:
            if s.get("enabled", True) and not s.get("ok"):
                report.messages.append(
                    f"mcp fail: {s.get('name')}: {s.get('detail')}"
                )
                report.needs_gateway_reload = True
        # iris-control live 미연결이면 재연결 유도
        for s in audited:
            if s.get("name") == "iris-control" and "not live" in str(s.get("detail") or ""):
                report.needs_gateway_reload = True
    except Exception as exc:  # noqa: BLE001
        report.messages.append(f"mcp audit skip: {exc}")

    if reconnect_gateway and report.mcp_installed:
        # Iris가 막 살아난 뒤엔 config가 같아도 Hermes MCP 서브프로세스를
        # 다시 붙여야 도구가 활성화된다. (이전 "healthy skip"은 연결 유지 실패 원인)
        report.needs_gateway_reload = True
        report.messages.append(
            "reconnect_gateway: Iris start — reload Hermes so MCP attaches to live control"
        )

    try:
        sync_state_path().write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return report


def _self_check() -> None:
    root = project_root()
    assert (root / "iris" / "mcp" / "iris_control_stdio.py").is_file()
    entry = root / "integrations" / "hermes-mcp" / "iris_control_stdio_entry.py"
    assert entry.is_file(), entry
    src = repo_skills_iris_control_dir()
    assert src.is_dir(), src
    for name in SKILL_NAMES:
        assert (src / name / "SKILL.md").is_file(), name
    block = desired_mcp_block(root)
    assert Path(block["args"][-1]).is_file(), block["args"]
    assert "-u" in block["args"]
    assert _mcp_equivalent(block, block)
    mobile = desired_mobile_mcp_block()
    assert mobile["command"] == "npx"
    assert mobile["args"] == ["-y", "@mobilenext/mobile-mcp@latest"]
    assert mobile["env"]["ANDROID_HOME"] == mobile["env"]["ANDROID_SDK_ROOT"]
    assert "platform-tools" in str(mobile["env"].get("PATH") or "")
    assert _mcp_equivalent(mobile, mobile)
    # live npx spawn skipped when Node missing
    if not shutil.which("npx"):
        print("hermes_iris_control_sync self-check: npx missing (mobile-mcp spawn skipped)")
    audited = audit_all_mcp_servers()
    assert isinstance(audited, list)
    print("hermes_iris_control_sync self-check ok", root, "mcp", len(audited))


if __name__ == "__main__":
    if "--apply" in sys.argv:
        r = sync_iris_control(reconnect_gateway=True)
        payload = json.dumps(asdict(r), ensure_ascii=False, indent=2)
        try:
            print(payload)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((payload + "\n").encode("utf-8", errors="replace"))
        raise SystemExit(0 if r.ok else 1)
    _self_check()
