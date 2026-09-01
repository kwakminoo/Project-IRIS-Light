"""IRIS IDE (Eclipse Theia) runtime — install, start, bridge, shutdown."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from iris.system.hermes_iris_control_sync import iris_state_dir, project_root
from iris.system.node_runtime import (
    NODE_DOWNLOAD_URL,
    install_node_winget,
    is_node_ready,
    node_executable,
)

THEIA_VERSION = "1.74.0"
RUNTIME_NAME = "iris-ide"


def is_iris_ide_demo() -> bool:
    return os.environ.get("IRIS_IDE_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


def runtime_source_dir() -> Path:
    return project_root() / "integrations" / "iris-ide"


def runtime_install_dir() -> Path:
    return iris_state_dir() / "runtimes" / RUNTIME_NAME


def runtime_state_path() -> Path:
    d = iris_state_dir() / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d / "iris_ide_state.json"


def iris_ide_config_dir() -> Path:
    """Theia user-data (installed marketplace extensions persist here)."""
    d = iris_state_dir() / "iris-ide" / "user-data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class IrisIdeStatus:
    installed: bool
    damaged: bool
    node_ok: bool
    detail: str
    theia_port: int | None = None
    bridge_port: int | None = None


ProgressFn = Callable[[str], None]


class IrisIdeRuntimeManager:
    """Theia browser backend + IRIS bridge lifecycle."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._bridge_proc: subprocess.Popen[str] | None = None
        self._theia_port: int | None = None
        self._bridge_port: int | None = None
        self._token: str = ""
        self._workspace: str = ""
        self._lock = threading.Lock()

    def status(self) -> IrisIdeStatus:
        node_ok, node_msg = is_node_ready()
        inst = self.is_installed()
        damaged = bool(node_ok and runtime_install_dir().is_dir() and not inst)
        if is_iris_ide_demo():
            return IrisIdeStatus(True, False, node_ok, "[demo] IRIS IDE ready", 3000, 3001)
        if not node_ok:
            return IrisIdeStatus(False, False, False, node_msg)
        if not inst:
            label = "IRIS IDE 미설치" if not damaged else "IRIS IDE 손상됨"
            return IrisIdeStatus(False, damaged, True, label)
        st = self._read_state()
        return IrisIdeStatus(
            True,
            False,
            True,
            f"IRIS IDE 설치됨 (Theia {THEIA_VERSION})",
            int(st.get("port") or 0) or None,
            int(st.get("bridge_port") or 0) or None,
        )

    def is_installed(self) -> bool:
        if is_iris_ide_demo():
            return True
        root = runtime_install_dir()
        pkg = root / "package.json"
        built = root / "lib" / "frontend" / "index.html"
        bridge = root / "bridge" / "standalone-bridge.js"
        plugins = root / "plugins"
        core = root / "node_modules" / "@theia" / "core" / "package.json"
        if not (pkg.is_file() and built.is_file() and bridge.is_file() and core.is_file()):
            return False
        if not plugins.is_dir() or not any(plugins.iterdir()):
            return False
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = data.get("dependencies") or {}
            ver = str(deps.get("@theia/core") or "")
            return ver.startswith("1.74")
        except (OSError, json.JSONDecodeError):
            return False

    def verify_installation(self) -> tuple[bool, str]:
        if is_iris_ide_demo():
            return True, "[demo] verified"
        st = self.status()
        if not st.node_ok:
            return False, st.detail
        if not self.is_installed():
            return False, "Theia build output 또는 node_modules가 없습니다 (손상됨)"
        return True, "설치 검증 OK"

    def install(
        self,
        *,
        progress: ProgressFn | None = None,
        run_streamed: Callable[..., Any] | None = None,
    ) -> tuple[bool, str]:
        if is_iris_ide_demo():
            return True, "[demo] IRIS IDE 설치됨"
        ok_node, _node_msg = is_node_ready()
        if not ok_node:
            ok_inst, inst_msg = install_node_winget(run_streamed=run_streamed)
            if not ok_inst:
                return False, inst_msg
        src = runtime_source_dir()
        if not (src / "package.json").is_file():
            return False, f"소스 없음: {src}"
        dest = runtime_install_dir()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("node_modules", "lib", ".theia"))
        self._emit(progress, "yarn install…")
        yarn_ok, yarn_msg = self._run_yarn(dest, ["install", "--frozen-lockfile"], progress, run_streamed)
        if not yarn_ok:
            yarn_ok, yarn_msg = self._run_yarn(dest, ["install"], progress, run_streamed)
        if not yarn_ok:
            return False, yarn_msg
        self._emit(progress, "TypeScript compile…")
        tsc = dest / "node_modules" / "typescript" / "bin" / "tsc"
        ok_tsc, tsc_msg = self._run_cmd(
            [node_executable(), str(tsc)],
            cwd=str(dest),
            progress=progress,
            run_streamed=run_streamed,
        )
        if not ok_tsc:
            return False, tsc_msg
        self._emit(progress, "theia build…")
        ok_build, build_msg = self._run_yarn(dest, ["run", "build"], progress, run_streamed)
        if not ok_build:
            return False, build_msg
        self._sync_build_patch(dest, progress=progress, run_streamed=run_streamed)
        return self.verify_installation()

    def repair(self, **kwargs: Any) -> tuple[bool, str]:
        return self.install(**kwargs)

    def _sync_build_patch(
        self,
        dest: Path,
        *,
        progress: ProgressFn | None = None,
        run_streamed: Callable[..., Any] | None = None,
    ) -> None:
        """워크스페이스 최신 IRIS IDE 확장/번들을 설치본에 반영."""
        src = runtime_source_dir()
        for rel in (
            "lib/browser/iris-ide-frontend-contribution.js",
            "lib/browser/iris-ide-frontend-module.js",
            "lib/frontend/bundle.js",
        ):
            s = src / rel
            if s.is_file():
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, out)
        patch_src = src / "scripts" / "patch-theia-build.js"
        patch_js = dest / "scripts" / "patch-theia-build.js"
        if patch_src.is_file():
            patch_js.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(patch_src, patch_js)
        if patch_js.is_file():
            self._emit(progress, "IRIS IDE build patch…")
            self._run_cmd(
                [node_executable(), str(patch_js)],
                cwd=str(dest),
                progress=progress,
                run_streamed=run_streamed,
                timeout=180.0,
            )

    def start(self, project_root_path: str = "") -> tuple[bool, str]:
        with self._lock:
            if is_iris_ide_demo():
                self._theia_port = 3000
                self._bridge_port = 3001
                self._token = "demo-token"
                self._workspace = project_root_path or str(project_root())
                self._write_state({"pid": 0, "port": 3000, "bridge_port": 3001, "token": self._token})
                return True, "demo"
            ok, msg = self.verify_installation()
            if not ok:
                return False, msg
            if self._proc is not None and self._proc.poll() is None:
                if project_root_path:
                    self.open_project(project_root_path)
                return True, "already running"
            root = Path(project_root_path or "").expanduser()
            if project_root_path and not root.is_dir():
                return False, f"not a directory: {project_root_path}"
            self._workspace = str(root.resolve()) if root.is_dir() else str(project_root().resolve())
            self._theia_port = _free_port()
            self._bridge_port = _free_port()
        self._token = secrets.token_urlsafe(24)
        env = os.environ.copy()
        env["PORT"] = str(self._theia_port)
        env["THEIA_CONFIG_DIR"] = str(iris_ide_config_dir())
        env["IRIS_IDE_WORKSPACE"] = self._workspace
        env["IRIS_IDE_BRIDGE_PORT"] = str(self._bridge_port)
        env["IRIS_IDE_BRIDGE_TOKEN"] = self._token
        env["IRIS_IDE_STATE_FILE"] = str(runtime_state_path())
        node = node_executable()
        theia_cli = runtime_install_dir() / "node_modules" / "@theia" / "cli" / "bin" / "theia.js"
        bridge_js = runtime_install_dir() / "bridge" / "standalone-bridge.js"
        if not bridge_js.is_file():
            bridge_js = runtime_source_dir() / "bridge" / "standalone-bridge.js"
        if not theia_cli.is_file():
            return False, "theia CLI missing — repair/install 필요"
        if not bridge_js.is_file():
            return False, "bridge script missing"
        install_root = runtime_install_dir()
        plugins_dir = install_root / "plugins"
        router_config = install_root / "ovsx-router-config.json"
        theia_args = [
            node,
            str(theia_cli),
            "start",
            "--hostname=127.0.0.1",
            f"--port={self._theia_port}",
            f"--plugins=local-dir:{plugins_dir}",
        ]
        if router_config.is_file():
            theia_args.append(f"--ovsx-router-config={router_config}")
        theia_args.append(self._workspace)
        kwargs_base: dict[str, Any] = {
            "cwd": str(runtime_install_dir()),
            "env": env,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs_base["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            self._bridge_proc = subprocess.Popen([node, str(bridge_js)], **kwargs_base)  # noqa: S603
            self._proc = subprocess.Popen(theia_args, **kwargs_base)  # noqa: S603
        except OSError as exc:
            return False, str(exc)
        self._write_state(
            {
                "pid": self._proc.pid,
                "bridge_pid": self._bridge_proc.pid if self._bridge_proc else 0,
                "port": self._theia_port,
                "bridge_port": self._bridge_port,
                "token": self._token,
                "workspace": self._workspace,
            }
        )
        ok_ready, detail = self.wait_until_ready(timeout_sec=120.0)
        if not ok_ready:
            self.stop()
            return False, detail
        return True, detail

    def wait_until_ready(self, *, timeout_sec: float = 90.0) -> tuple[bool, str]:
        if is_iris_ide_demo():
            return True, "demo ready"
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                return False, "Theia process exited early"
            if self.health():
                st = self._read_state()
                if int(st.get("bridge_port") or 0):
                    self._bridge_port = int(st["bridge_port"])
                return True, "Theia ready"
            time.sleep(0.35)
        return False, "Theia health timeout"

    def base_url(self) -> str:
        port = self._theia_port or int(self._read_state().get("port") or 0)
        return f"http://127.0.0.1:{port}" if port else ""

    @property
    def bridge_port(self) -> int | None:
        return self._bridge_port or int(self._read_state().get("bridge_port") or 0) or None

    def bridge_base_url(self) -> str:
        port = self.bridge_port or int(self._read_state().get("bridge_port") or 0)
        return f"http://127.0.0.1:{port}" if port else ""

    def bridge_token(self) -> str:
        if self._token:
            return self._token
        return str(self._read_state().get("token") or "")

    @property
    def runtime_pid(self) -> int | None:
        if self._proc is not None and self._proc.poll() is None:
            return int(self._proc.pid)
        return None

    @property
    def workspace(self) -> str:
        return self._workspace

    def health(self) -> bool:
        if is_iris_ide_demo():
            return True
        url = self.base_url()
        if not url:
            return False
        try:
            with urlopen(Request(url, method="GET"), timeout=2.0) as resp:
                if not (200 <= resp.status < 500):
                    return False
        except (URLError, TimeoutError, OSError):
            return False
        return self.bridge_health()

    def bridge_health(self) -> bool:
        url = self.bridge_base_url()
        if not url:
            return False
        token = self.bridge_token()
        req = Request(f"{url}/health", method="POST", data=b"{}")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urlopen(req, timeout=2.0) as resp:
                return 200 <= resp.status < 500
        except (URLError, TimeoutError, OSError):
            return False

    def open_project(self, project_root_path: str) -> tuple[bool, str]:
        root = Path(project_root_path).expanduser()
        if not root.is_dir():
            return False, f"not a directory: {project_root_path}"
        self._workspace = str(root.resolve())
        from iris.infrastructure.iris_ide_client import IrisIdeClient

        client = IrisIdeClient(base_url=self.bridge_base_url(), token=self.bridge_token())
        try:
            client.get_workspace()
            return True, self._workspace
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def stop(self) -> None:
        with self._lock:
            for proc in (self._proc, self._bridge_proc):
                if proc is not None and proc.poll() is None:
                    if sys.platform == "win32":
                        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                            creationflags=flags,
                            timeout=8,
                            check=False,
                        )
                    else:
                        try:
                            proc.terminate()
                            proc.wait(timeout=5)
                        except (OSError, subprocess.TimeoutExpired):
                            proc.kill()
            self._proc = None
            self._bridge_proc = None
            self._clear_state()

    def _read_state(self) -> dict[str, Any]:
        path = runtime_state_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, payload: dict[str, Any]) -> None:
        path = runtime_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def _clear_state(self) -> None:
        path = runtime_state_path()
        try:
            path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if path.is_file():
                path.unlink()

    @staticmethod
    def _emit(progress: ProgressFn | None, msg: str) -> None:
        if progress:
            progress(msg)

    def _run_yarn(
        self,
        cwd: Path,
        args: list[str],
        progress: ProgressFn | None,
        run_streamed: Callable[..., Any] | None,
    ) -> tuple[bool, str]:
        yarn = shutil.which("yarn") or shutil.which("yarn.cmd")
        if yarn:
            cmd = [yarn, *args]
        else:
            npm = shutil.which("npm") or node_executable()
            cmd = [npm, "exec", "--yes", "yarn@1.22.22", *args]
        return self._run_cmd(cmd, cwd=str(cwd), progress=progress, run_streamed=run_streamed)

    def _run_cmd(
        self,
        cmd: list[str],
        *,
        cwd: str,
        progress: ProgressFn | None,
        run_streamed: Callable[..., Any] | None,
        timeout: float = 3600.0,
    ) -> tuple[bool, str]:
        self._emit(progress, " ".join(cmd[:4]) + "…")
        try:
            if run_streamed is not None:
                proc = run_streamed(cmd, cwd=cwd, timeout=timeout, hard_timeout=timeout + 60, hidden=True)
                if proc.returncode != 0:
                    tail = (proc.stdout or "")[-240:]
                    return False, tail or f"exit {proc.returncode}"
                return True, "ok"
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "")[-240:]
                return False, tail or f"exit {proc.returncode}"
            return True, "ok"
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)


_MANAGER: IrisIdeRuntimeManager | None = None


def shared_iris_ide_runtime() -> IrisIdeRuntimeManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = IrisIdeRuntimeManager()
    return _MANAGER


def _self_check() -> None:
    mgr = IrisIdeRuntimeManager()
    st = mgr.status()
    assert isinstance(st.installed, bool)
    print("iris_ide_runtime ok", st.detail, NODE_DOWNLOAD_URL)


if __name__ == "__main__":
    _self_check()
