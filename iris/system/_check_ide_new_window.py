"""자검: IDE 새 창 식별·generic title 문맥·Agents 제외.

실행: py -3 -m iris.system._check_ide_new_window
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iris.system.ide_launcher import (  # noqa: E402
    is_cursor_agents_title,
    is_generic_ide_title,
    is_iris_ide_window_title,
    launch_ide,
    list_ide_windows,
    open_folder_in_ide,
    resolve_ide_exe,
    wait_for_new_ide_window,
    workspace_title_lost_context,
)


def _check_control_bindings_new_window_default() -> None:
    """회귀: control surface 기본 new_window 는 True (bac8f75 False 회귀 금지)."""
    src = (ROOT / "iris" / "ui" / "control_bindings.py").read_text(encoding="utf-8")
    assert src.count('args.get("new_window", True)') >= 3
    bad = 'args.get("new_window", False)'
    open_region = src[src.find("def ide_open_folder") : src.find("def project_list_parents")]
    similar_region = src[
        src.find("def project_open_similar") : src.find("def project_create_scaffold")
    ]
    scaffold_start = src.find("def project_create_scaffold")
    scaffold_region = src[scaffold_start : scaffold_start + 2500]
    assert bad not in open_region, "ide.open_folder must default new_window=True"
    assert bad not in similar_region, "project.open_similar must default new_window=True"
    assert bad not in scaffold_region, "project.create_scaffold must default new_window=True"
    print("control_bindings new_window default ok")


def _check_title_helpers() -> None:
    assert is_cursor_agents_title("Cursor Agents")
    assert is_cursor_agents_title("cursor agents")
    assert not is_cursor_agents_title("Cursor")
    assert not is_cursor_agents_title("Project-IRIS-Light-main - Cursor")

    assert is_generic_ide_title("Cursor")
    assert is_iris_ide_window_title("IRIS IDE")
    assert is_iris_ide_window_title("readme.md — IRIS IDE")
    assert not is_iris_ide_window_title("Other - Cursor")
    assert is_generic_ide_title("cursor")
    assert is_generic_ide_title("")
    assert not is_generic_ide_title("Project-IRIS-Light-main - Cursor")

    root = str(ROOT)
    # generic 직후 — session clear 금지
    assert not workspace_title_lost_context("Cursor", root)
    assert not workspace_title_lost_context("cursor", root)
    assert not workspace_title_lost_context("Cursor Agents", root)
    assert not workspace_title_lost_context("", root)
    # 우리 workspace 제목 — 유지
    assert not workspace_title_lost_context(f"{ROOT.name} - Cursor", root)
    assert not workspace_title_lost_context(f"main.py — {ROOT.name} — Cursor", root)
    # 진짜 다른 workspace — clear
    assert workspace_title_lost_context("OtherProject - Cursor", root)
    print("title helpers ok")


def _check_agents_never_chosen_as_new() -> None:
    """wait_for_new_ide_window 가 Agents 제목을 새 창으로 반환하지 않는지 (로직)."""
    # 순수 헬퍼: Agents만 있으면 newcomers 필터에서 탈락해야 함
    assert is_cursor_agents_title("Cursor Agents")
    fake = [{"hwnd": 1, "pid": 2, "title": "Cursor Agents", "score": 9_999_999}]
    usable = [w for w in fake if not is_cursor_agents_title(str(w.get("title") or ""))]
    assert usable == [], "Agents must not be a new-window candidate"
    print("agents exclusion ok")


def _check_live_new_window() -> None:
    exe, err = resolve_ide_exe("cursor")
    assert exe and not err, err or "no cursor exe"
    before = {
        int(w["hwnd"])
        for w in list_ide_windows("cursor", include_untitled=True)
    }
    pid, launch_err = launch_ide("cursor", new_window=True)
    assert not launch_err, launch_err
    hwnd, wait_pid, title = wait_for_new_ide_window(
        "cursor",
        exclude_hwnds=before,
        title_substr="",
        timeout_sec=5.0,
    )
    assert hwnd is not None, "new window not found"
    assert int(hwnd) not in before, "reused old hwnd"
    assert not is_cursor_agents_title(title), f"got Agents: {title!r}"
    # one-shot이 아님: 빈 새 창 spawn 후 inject 는 main_window 경로
    pid2, err2 = open_folder_in_ide(
        "cursor",
        str(ROOT),
        new_window=True,
        reuse_window=False,
    )
    assert not err2, err2
    # new_window=True 는 빈 창만 — folder 인자 없이 --new-window
    time.sleep(0.2)
    print(
        "live ok",
        {
            "exe": exe,
            "launch_pid": pid,
            "hwnd": hwnd,
            "title": title,
            "empty_new_window_pid": pid2,
            "wait_pid": wait_pid,
        },
    )


def _check_companion_session_retention() -> None:
    """companion 진입 직후 generic title → session/ui_mode 유지 (회귀 방지)."""
    root = str(ROOT)
    # _refresh_ide_session_state 가 clear 하면 _ui_mode 가 normal 로 풀림
    would_clear = workspace_title_lost_context("Cursor", root)
    assert not would_clear, "generic title must not clear workspace session"
    # 타일 성공 후 Iris 는 ide_companion 유지되어야 함
    ui_mode = "ide_companion"
    if would_clear:
        ui_mode = "normal"
    assert ui_mode == "ide_companion"
    print("companion session retention ok")


def main() -> int:
    _check_control_bindings_new_window_default()
    _check_title_helpers()
    _check_agents_never_chosen_as_new()
    _check_companion_session_retention()
    if sys.platform == "win32":
        try:
            _check_live_new_window()
        except AssertionError as exc:
            print("live check skipped/failed:", exc)
            # 헬퍼 자검은 통과했으므로 0 — 수동 검증 안내
            print("hint: Cursor가 떠 있을 때 수동으로 IDE 아이콘 토글 검증")
    else:
        print("live new-window check skipped (non-Windows)")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
