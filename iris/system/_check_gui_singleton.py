"""두 번째 GUI 획득은 실패해야 한다 (control 서버 이중 기동 방지)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from iris.system.gui_singleton import acquire_gui_singleton


def _subprocess_kwargs() -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 20,
        "env": env,
    }
    try:
        from iris.system.win_subprocess import no_window_kwargs

        kwargs.update(no_window_kwargs())
    except Exception:
        pass
    return kwargs


def _assert_same_process(root: Path) -> None:
    """Fresh interpreter so process-global mutex state starts clean."""
    repo = str(Path(__file__).resolve().parents[2])
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {repo!r})\n"
        "from iris.system.gui_singleton import acquire_gui_singleton\n"
        f"root = Path({str(root)!r})\n"
        "ok1, msg1 = acquire_gui_singleton(data_dir=root)\n"
        "assert ok1, msg1\n"
        "ok2, msg2 = acquire_gui_singleton(data_dir=root)\n"
        "assert not ok2, 'second acquire must fail'\n"
        "assert '이미 실행' in msg2\n"
        "print('SAME_OK', flush=True)\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], **_subprocess_kwargs())
    assert proc.returncode == 0, f"same-process check failed: {proc.stdout!r} {proc.stderr!r}"
    assert "SAME_OK" in proc.stdout


def _assert_cross_process(root: Path) -> None:
    ok, msg = acquire_gui_singleton(data_dir=root)
    assert ok, msg
    repo = str(Path(__file__).resolve().parents[2])
    child = (
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {repo!r})\n"
        "from iris.system.gui_singleton import acquire_gui_singleton\n"
        f"ok, msg = acquire_gui_singleton(data_dir=Path({str(root)!r}))\n"
        "print('CHILD', ok, repr(msg), flush=True)\n"
        "raise SystemExit(0 if ok is False else 2)\n"
    )
    proc = subprocess.run([sys.executable, "-c", child], **_subprocess_kwargs())
    assert proc.returncode == 0, (
        f"cross-process acquire must fail: rc={proc.returncode} "
        f"out={proc.stdout!r} err={proc.stderr!r}"
    )
    assert "CHILD False" in proc.stdout, proc.stdout


def _assert_abandoned_reacquire(root: Path) -> None:
    """Child holds mutex, hard-killed → next acquire must succeed (abandoned ok)."""
    if os.name != "nt":
        return
    repo = str(Path(__file__).resolve().parents[2])
    root_s = str(root)
    holder = (
        "import sys, time\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {repo!r})\n"
        "from iris.system.gui_singleton import acquire_gui_singleton\n"
        f"ok, msg = acquire_gui_singleton(data_dir=Path({root_s!r}))\n"
        "assert ok, msg\n"
        "print('HELD', flush=True)\n"
        "time.sleep(60)\n"
    )
    # Fresh interpreter so process-global _MUTEX_HANDLE starts clean.
    # Keep an extra mutex handle open across kill so the named object stays
    # abandoned (not destroyed) and acquire must take WAIT_ABANDONED.
    script = (
        "import ctypes, subprocess, sys, time\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {repo!r})\n"
        f"holder = {holder!r}\n"
        f"root = {root_s!r}\n"
        "kw = {}\n"
        "try:\n"
        "    from iris.system.win_subprocess import no_window_kwargs\n"
        "    kw.update(no_window_kwargs())\n"
        "except Exception:\n"
        "    pass\n"
        "proc = subprocess.Popen(\n"
        "    [sys.executable, '-c', holder],\n"
        "    stdout=subprocess.PIPE, stderr=subprocess.PIPE,\n"
        "    text=True, encoding='utf-8', errors='replace', **kw,\n"
        ")\n"
        "line = ''\n"
        "deadline = time.time() + 10\n"
        "while time.time() < deadline:\n"
        "    line = proc.stdout.readline()\n"
        "    if 'HELD' in line:\n"
        "        break\n"
        "assert 'HELD' in line, (line, proc.stderr.read())\n"
        "from iris.system.gui_singleton import _mutex_name, acquire_gui_singleton\n"
        "k32 = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "k32.CreateMutexW.restype = ctypes.c_void_p\n"
        "keep = k32.CreateMutexW(None, False, _mutex_name(Path(root)))\n"
        "assert keep, 'pin handle'\n"
        "proc.kill()\n"
        "proc.wait(timeout=10)\n"
        "ok, msg = acquire_gui_singleton(data_dir=Path(root))\n"
        "k32.CloseHandle(keep)\n"
        "assert ok, msg\n"
        "print('ABANDONED_OK', flush=True)\n"
    )
    kw = _subprocess_kwargs()
    kw["timeout"] = 30
    proc = subprocess.run([sys.executable, "-c", script], **kw)
    assert proc.returncode == 0, (
        f"abandoned reacquire failed: rc={proc.returncode} "
        f"out={proc.stdout!r} err={proc.stderr!r}"
    )
    assert "ABANDONED_OK" in proc.stdout, proc.stdout


def main() -> None:
    same_root = Path(tempfile.mkdtemp(prefix="iris-gui-lock-"))
    _assert_same_process(same_root)

    xproc_root = Path(tempfile.mkdtemp(prefix="iris-gui-lock-xproc-"))
    _assert_cross_process(xproc_root)

    aband_root = Path(tempfile.mkdtemp(prefix="iris-gui-lock-aband-"))
    _assert_abandoned_reacquire(aband_root)
    print("gui singleton ok")


if __name__ == "__main__":
    main()
