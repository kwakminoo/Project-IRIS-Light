"""자검: Cursor GUI exe --new-window 가 Agents와 다른 새 hwnd 를 만드는지."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iris.system.ide_launcher import (  # noqa: E402
    launch_ide,
    list_ide_windows,
    open_folder_in_ide,
    resolve_ide_exe,
    wait_for_new_ide_window,
)


def main() -> int:
    exe, err = resolve_ide_exe("cursor")
    assert exe and not err, err or "no cursor exe"
    before = {int(w["hwnd"]) for w in list_ide_windows("cursor")}
    pid, launch_err = launch_ide("cursor", new_window=True)
    assert not launch_err, launch_err
    hwnd, wait_pid, title = wait_for_new_ide_window(
        "cursor",
        exclude_hwnds=before,
        title_substr="",
        timeout_sec=12.0,
    )
    assert hwnd is not None, "new window not found"
    assert int(hwnd) not in before, "reused old hwnd"
    assert str(title).strip().lower() != "cursor agents", f"got Agents: {title!r}"
    # new_window 경로는 폴더 없이 GUI exe만
    pid2, err2 = open_folder_in_ide(
        "cursor",
        str(ROOT),
        new_window=True,
        reuse_window=False,
    )
    assert not err2, err2
    time.sleep(0.2)
    print("ok", {"exe": exe, "launch_pid": pid, "hwnd": hwnd, "title": title, "spawn_pid": pid2})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
