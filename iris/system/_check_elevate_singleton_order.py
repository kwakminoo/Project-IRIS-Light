"""elevate / singleton / venv-stub launch contracts.

1) main() calls elevate before acquire_gui_singleton (source order).
2) successful relaunch_as_admin → caller must exit (mocked ShellExecute).
3) resolve_gui_pythonw launch leaves one -m iris process (no venv stub parent).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def _assert_elevate_before_singleton_in_source() -> None:
    main_path = ROOT / "iris" / "__main__.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    elevate_line: int | None = None
    singleton_line: int | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name == "_maybe_elevate_on_startup":
            elevate_line = node.lineno
        if name == "acquire_gui_singleton":
            singleton_line = node.lineno
    assert elevate_line is not None, "missing _maybe_elevate_on_startup call"
    assert singleton_line is not None, "missing acquire_gui_singleton call"
    assert elevate_line < singleton_line, (
        f"elevate must precede singleton: elevate L{elevate_line} singleton L{singleton_line}"
    )
    print("ORDER_OK", elevate_line, singleton_line)


def _assert_relaunch_sets_flag_and_parent_exits_contract() -> None:
    if sys.platform != "win32":
        print("RELAUNCH_SKIP non-windows")
        return
    from iris.learning import elevation

    calls: list[tuple] = []

    def fake_shell(*args):
        calls.append(args)
        return 42  # > 32 → success

    with mock.patch.object(elevation, "is_elevated", return_value=False):
        with mock.patch("ctypes.windll.shell32.ShellExecuteW", side_effect=fake_shell):
            os.environ.pop("IRIS_ELEVATED_CHILD", None)
            ok = elevation.relaunch_as_admin()
    assert ok is True, ok
    assert calls, "ShellExecuteW not called"
    assert os.environ.get("IRIS_ELEVATED_CHILD") == "1"
    # Contract checked by __main__: if _maybe_elevate_on_startup(): sys.exit(0)
    src = (ROOT / "iris" / "__main__.py").read_text(encoding="utf-8")
    assert "if _maybe_elevate_on_startup():" in src
    assert "sys.exit(0)" in src.split("if _maybe_elevate_on_startup():", 1)[1][:200]
    print("RELAUNCH_OK")


def _iris_pythonw_procs() -> list:
    import psutil

    rows = []
    for p in psutil.process_iter(["pid", "ppid", "exe", "cmdline", "name"]):
        try:
            if "pythonw" not in (p.info.get("name") or "").lower():
                continue
            cl = p.info.get("cmdline") or []
            if "-m" in cl and "iris" in cl:
                idx = cl.index("-m")
                if idx + 1 < len(cl) and cl[idx + 1] == "iris":
                    rows.append(p)
        except Exception:
            continue
    return rows


def _assert_single_process_via_gui_python() -> None:
    if sys.platform != "win32":
        print("SINGLE_SKIP non-windows")
        return
    import psutil

    from iris.system.gui_python import gui_launch_env, resolve_gui_pythonw

    for p in _iris_pythonw_procs():
        try:
            p.kill()
        except Exception:
            pass
    time.sleep(1)

    py = resolve_gui_pythonw(ROOT)
    env = gui_launch_env(ROOT)
    proc = subprocess.Popen([str(py), "-m", "iris"], cwd=str(ROOT), env=env)
    try:
        deadline = time.time() + 12
        live: list = []
        while time.time() < deadline:
            live = _iris_pythonw_procs()
            if any(p.pid == proc.pid or p.ppid() == proc.pid for p in live):
                # Wait until main has had time to settle; require exactly one.
                time.sleep(2)
                live = _iris_pythonw_procs()
                break
            time.sleep(0.4)
        assert len(live) == 1, (
            f"expected one -m iris pythonw, got {[(p.pid, p.ppid(), p.exe()) for p in live]}"
        )
        only = live[0]
        # Must be the real base interpreter, not Scripts stub waiting on a child.
        stub = ROOT / ".venv" / "Scripts" / "pythonw.exe"
        if stub.is_file():
            assert Path(only.exe()).resolve() != stub.resolve(), only.exe()
        print("SINGLE_OK", only.pid, only.exe())
    finally:
        for p in _iris_pythonw_procs():
            try:
                p.kill()
            except Exception:
                pass
        try:
            proc.kill()
        except Exception:
            pass


def main() -> None:
    _assert_elevate_before_singleton_in_source()
    _assert_relaunch_sets_flag_and_parent_exits_contract()
    _assert_single_process_via_gui_python()
    print("elevate singleton order ok")


if __name__ == "__main__":
    main()
