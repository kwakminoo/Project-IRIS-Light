"""IDE 경로 해석 · 실행 · 이미 실행 중 탐지 (Windows 우선).

ponytail: 카탈로그는 대표 설치 경로만 — Toolbox/포터블은 프로필 ide_exe_path로 덮어쓴다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IdeSpec:
    id: str
    name: str
    process_names: tuple[str, ...]
    exe_candidates: tuple[str, ...]
    install_url: str
    title_hints: tuple[str, ...] = ()
    cli_candidates: tuple[str, ...] = ()
    which_names: tuple[str, ...] = ()
    which_exclude: tuple[str, ...] = ()


def _local_appdata() -> str:
    return os.environ.get("LOCALAPPDATA", "")


def _program_files() -> str:
    return os.environ.get("ProgramFiles", r"C:\Program Files")


def _program_files_x86() -> str:
    return os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


def ide_catalog() -> tuple[IdeSpec, ...]:
    la = _local_appdata()
    pf = _program_files()
    pf86 = _program_files_x86()
    return (
        IdeSpec(
            id="cursor",
            name="Cursor",
            process_names=("Cursor.exe",),
            exe_candidates=(
                rf"{la}\Programs\cursor\Cursor.exe",
                rf"{la}\Programs\Cursor\Cursor.exe",
            ),
            cli_candidates=(
                rf"{la}\Programs\cursor\resources\app\bin\cursor.cmd",
            ),
            which_names=("cursor",),
            title_hints=("Cursor",),
            install_url="https://cursor.com/download",
        ),
        IdeSpec(
            id="vscode",
            name="VS Code",
            process_names=("Code.exe",),
            exe_candidates=(
                rf"{la}\Programs\Microsoft VS Code\Code.exe",
                rf"{pf}\Microsoft VS Code\Code.exe",
            ),
            cli_candidates=(
                rf"{la}\Programs\Microsoft VS Code\bin\code.cmd",
                rf"{pf}\Microsoft VS Code\bin\code.cmd",
            ),
            which_names=("code",),
            # PATH의 code.cmd가 Cursor codeBin일 수 있음
            which_exclude=("cursor\\resources\\app\\codeBin", "cursor/resources/app/codeBin"),
            title_hints=("Visual Studio Code", "Code - "),
            install_url="https://code.visualstudio.com/download",
        ),
        IdeSpec(
            id="vs",
            name="Visual Studio",
            process_names=("devenv.exe",),
            exe_candidates=(
                rf"{pf}\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe",
                rf"{pf}\Microsoft Visual Studio\2022\Professional\Common7\IDE\devenv.exe",
                rf"{pf}\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\devenv.exe",
                rf"{pf86}\Microsoft Visual Studio\2019\Community\Common7\IDE\devenv.exe",
            ),
            title_hints=("Microsoft Visual Studio",),
            install_url="https://visualstudio.microsoft.com/downloads/",
        ),
        IdeSpec(
            id="pycharm",
            name="PyCharm",
            process_names=("pycharm64.exe", "pycharm.exe"),
            exe_candidates=(
                rf"{pf}\JetBrains\PyCharm 2024.3\bin\pycharm64.exe",
                rf"{pf}\JetBrains\PyCharm 2025.1\bin\pycharm64.exe",
                rf"{la}\Programs\PyCharm Community\bin\pycharm64.exe",
                rf"{la}\Programs\PyCharm Professional\bin\pycharm64.exe",
            ),
            title_hints=("PyCharm",),
            install_url="https://www.jetbrains.com/pycharm/download/",
        ),
        IdeSpec(
            id="intellij",
            name="IntelliJ IDEA",
            process_names=("idea64.exe", "idea.exe"),
            exe_candidates=(
                rf"{pf}\JetBrains\IntelliJ IDEA 2024.3\bin\idea64.exe",
                rf"{pf}\JetBrains\IntelliJ IDEA Community Edition 2024.3\bin\idea64.exe",
                rf"{la}\Programs\IntelliJ IDEA Community Edition\bin\idea64.exe",
            ),
            title_hints=("IntelliJ IDEA",),
            install_url="https://www.jetbrains.com/idea/download/",
        ),
        IdeSpec(
            id="webstorm",
            name="WebStorm",
            process_names=("webstorm64.exe", "webstorm.exe"),
            exe_candidates=(
                rf"{pf}\JetBrains\WebStorm 2024.3\bin\webstorm64.exe",
                rf"{la}\Programs\WebStorm\bin\webstorm64.exe",
            ),
            title_hints=("WebStorm",),
            install_url="https://www.jetbrains.com/webstorm/download/",
        ),
        IdeSpec(
            id="android_studio",
            name="Android Studio",
            process_names=("studio64.exe", "studio.exe"),
            exe_candidates=(
                rf"{pf}\Android\Android Studio\bin\studio64.exe",
                rf"{la}\Programs\Android Studio\bin\studio64.exe",
            ),
            title_hints=("Android Studio",),
            install_url="https://developer.android.com/studio",
        ),
        IdeSpec(
            id="sublime",
            name="Sublime Text",
            process_names=("sublime_text.exe",),
            exe_candidates=(
                rf"{pf}\Sublime Text\sublime_text.exe",
                rf"{la}\Programs\Sublime Text\sublime_text.exe",
            ),
            which_names=("subl",),
            title_hints=("Sublime Text",),
            install_url="https://www.sublimetext.com/download",
        ),
        IdeSpec(
            id="notepadpp",
            name="Notepad++",
            process_names=("notepad++.exe",),
            exe_candidates=(
                rf"{pf}\Notepad++\notepad++.exe",
                rf"{pf86}\Notepad++\notepad++.exe",
            ),
            title_hints=("Notepad++",),
            install_url="https://notepad-plus-plus.org/downloads/",
        ),
        IdeSpec(
            id="windsurf",
            name="Windsurf",
            process_names=("Windsurf.exe",),
            exe_candidates=(
                rf"{la}\Programs\Windsurf\Windsurf.exe",
                rf"{la}\Programs\windsurf\Windsurf.exe",
            ),
            title_hints=("Windsurf",),
            install_url="https://windsurf.com/download",
        ),
        IdeSpec(
            id="trae",
            name="Trae",
            process_names=("Trae.exe",),
            exe_candidates=(
                rf"{la}\Programs\Trae\Trae.exe",
                rf"{la}\Programs\trae\Trae.exe",
            ),
            title_hints=("Trae",),
            install_url="https://www.trae.ai/",
        ),
        IdeSpec(
            id="zed",
            name="Zed",
            process_names=("Zed.exe", "zed.exe"),
            exe_candidates=(
                rf"{la}\Programs\Zed\Zed.exe",
                rf"{pf}\Zed\Zed.exe",
            ),
            which_names=("zed",),
            title_hints=("Zed",),
            install_url="https://zed.dev/download",
        ),
        IdeSpec(
            id="rider",
            name="Rider",
            process_names=("rider64.exe", "rider.exe"),
            exe_candidates=(
                rf"{pf}\JetBrains\Rider 2024.3\bin\rider64.exe",
                rf"{la}\Programs\Rider\bin\rider64.exe",
            ),
            title_hints=("JetBrains Rider", "Rider"),
            install_url="https://www.jetbrains.com/rider/download/",
        ),
        IdeSpec(
            id="neovim",
            name="Neovim",
            process_names=("nvim-qt.exe", "nvim.exe"),
            exe_candidates=(
                rf"{pf}\Neovim\bin\nvim-qt.exe",
                rf"{la}\Programs\Neovim\bin\nvim-qt.exe",
                rf"{pf}\Neovim\bin\nvim.exe",
            ),
            which_names=("nvim-qt", "nvim"),
            title_hints=("Neovim", "nvim"),
            install_url="https://neovim.io/",
        ),
        IdeSpec(
            id="custom",
            name="사용자 지정",
            process_names=(),
            exe_candidates=(),
            install_url="",
            title_hints=(),
        ),
    )


def get_ide_spec(ide_id: str) -> IdeSpec | None:
    for spec in ide_catalog():
        if spec.id == ide_id:
            return spec
    return None


def _first_existing(paths: tuple[str, ...] | list[str]) -> str:
    for raw in paths:
        p = Path(_expand(raw))
        if p.is_file():
            return str(p.resolve())
    return ""


def _which_filtered(names: tuple[str, ...], exclude: tuple[str, ...]) -> str:
    for name in names:
        found = shutil.which(name)
        if not found:
            continue
        low = found.lower().replace("/", "\\")
        if any(ex.lower().replace("/", "\\") in low for ex in exclude):
            continue
        if Path(found).is_file():
            return str(Path(found).resolve())
    return ""


def resolve_ide_exe(
    preferred_ide: str,
    ide_exe_path: str = "",
) -> tuple[str, str]:
    """(exe_path, error). 성공 시 error는 빈 문자열."""
    custom = (ide_exe_path or "").strip()
    if custom:
        p = Path(_expand(custom))
        if p.is_file():
            return str(p.resolve()), ""
        return "", f"지정한 IDE 실행 파일이 없습니다: {custom}"

    ide_id = (preferred_ide or "cursor").strip().lower() or "cursor"
    if ide_id == "custom":
        return "", "사용자 지정 IDE 경로를 프로필에 입력하세요."

    spec = get_ide_spec(ide_id)
    if spec is None:
        return "", f"알 수 없는 IDE: {ide_id}"

    found = _first_existing(spec.exe_candidates)
    if found:
        return found, ""

    found = _which_filtered(spec.which_names, spec.which_exclude)
    if found:
        # which가 .cmd를 주면 GUI exe 후보를 다시 우선 — .cmd도 실행은 가능
        return found, ""

    return "", f"{spec.name}이(가) 설치되어 있지 않습니다."


def resolve_ide_cli(preferred_ide: str, ide_cli_path: str = "", ide_exe_path: str = "") -> str:
    custom = (ide_cli_path or "").strip()
    if custom and Path(_expand(custom)).is_file():
        return str(Path(_expand(custom)).resolve())
    spec = get_ide_spec((preferred_ide or "").strip().lower())
    if spec is None:
        return ""
    found = _first_existing(spec.cli_candidates)
    if found:
        return found
    exe, _ = resolve_ide_exe(preferred_ide, ide_exe_path)
    return exe


def is_ide_installed(preferred_ide: str, ide_exe_path: str = "") -> bool:
    exe, err = resolve_ide_exe(preferred_ide, ide_exe_path)
    return bool(exe) and not err


def find_running_ide(
    preferred_ide: str,
    ide_exe_path: str = "",
) -> tuple[int | None, int | None]:
    """(hwnd, pid). 없으면 (None, None)."""
    wins = list_ide_windows(preferred_ide, ide_exe_path)
    if not wins:
        return None, None
    # 면적(+제목 힌트) 최대 창
    best = max(wins, key=lambda w: w["score"])
    return int(best["hwnd"]), int(best["pid"])


def list_ide_windows(
    preferred_ide: str,
    ide_exe_path: str = "",
) -> list[dict]:
    """보이는 IDE top-level 창 목록: hwnd, pid, title, score."""
    if sys.platform != "win32":
        return []
    try:
        import psutil  # type: ignore
        import win32gui  # type: ignore
        import win32process  # type: ignore
    except Exception:
        return []

    ide_id = (preferred_ide or "cursor").strip().lower() or "cursor"
    spec = get_ide_spec(ide_id)
    process_names = {n.lower() for n in (spec.process_names if spec else ())}
    exe_resolved, _ = resolve_ide_exe(preferred_ide, ide_exe_path)
    exe_name = Path(exe_resolved).name.lower() if exe_resolved else ""
    if exe_name:
        process_names.add(exe_name)
    if not process_names:
        return []

    target_pids: set[int] = set()
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name not in process_names:
                continue
            if ide_id == "vscode":
                exe = (proc.info.get("exe") or "").lower().replace("/", "\\")
                if "\\cursor\\" in exe:
                    continue
            target_pids.add(int(proc.info["pid"]))
        except (psutil.Error, TypeError, ValueError):
            continue
    if not target_pids:
        return []

    title_hints = tuple(h.lower() for h in (spec.title_hints if spec else ()))
    found: list[dict] = []

    def _cb(hwnd: int, _arg: object) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.IsIconic(hwnd):
                return True
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid not in target_pids:
                return True
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            if not title:
                return True
            left, top, right, bot = win32gui.GetWindowRect(hwnd)
            w, h = right - left, bot - top
            if w < 200 or h < 120:
                return True
            score = w * h
            if title_hints and any(h in title.lower() for h in title_hints):
                score += 10_000_000
            found.append(
                {
                    "hwnd": int(hwnd),
                    "pid": int(pid),
                    "title": title,
                    "score": int(score),
                    "w": int(w),
                    "h": int(h),
                }
            )
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return []
    return found


def wait_for_new_ide_window(
    preferred_ide: str,
    *,
    ide_exe_path: str = "",
    exclude_hwnds: set[int] | None = None,
    title_substr: str = "",
    timeout_sec: float = 14.0,
    fallback_to_existing: bool = False,
) -> tuple[int | None, int | None, str]:
    """새로 뜬 IDE 창을 고른다. (hwnd, pid, title).

    exclude_hwnds: 열기 전에 있던 창 — 새 창만 반환(타임아웃 전 폴백 없음).
    title_substr: 폴더명 등 제목 힌트(있으면 가산).
    """
    exclude = set(exclude_hwnds or ())
    hint = (title_substr or "").strip().lower()
    deadline = time.monotonic() + timeout_sec
    last_pid: int | None = None
    while time.monotonic() < deadline:
        wins = list_ide_windows(preferred_ide, ide_exe_path)
        for w in wins:
            last_pid = int(w["pid"])
        newcomers = [w for w in wins if int(w["hwnd"]) not in exclude]
        if not newcomers:
            time.sleep(0.35)
            continue

        def _rank(w: dict) -> tuple:
            title = str(w.get("title") or "").lower()
            hit = 1 if hint and hint in title else 0
            return (hit, int(w.get("score") or 0))

        best = max(newcomers, key=_rank)
        title = str(best.get("title") or "")
        # 제목에 폴더명이 아직 안 붙었으면 잠깐 더 대기(단, 새 창은 이미 있음)
        if hint and hint not in title.lower() and (deadline - time.monotonic()) > 2.0:
            time.sleep(0.35)
            continue
        return int(best["hwnd"]), int(best["pid"]), title

    # ponytail: 세션 라우팅에서는 새 창을 못 찾았을 때 임의 기존 창으로 붙지 않는다.
    wins = list_ide_windows(preferred_ide, ide_exe_path)
    if fallback_to_existing and wins:
        best = max(wins, key=lambda w: int(w.get("score") or 0))
        return int(best["hwnd"]), int(best["pid"]), str(best.get("title") or "")
    return None, last_pid, ""


def launch_ide(
    preferred_ide: str,
    *,
    ide_exe_path: str = "",
    ide_cli_path: str = "",
    project_root: str = "",
    new_window: bool = False,
) -> tuple[int | None, str]:
    """IDE 실행. (pid, error).

    new_window=True 이면 --new-window 로 기본(웰컴) 화면을 띄우고
    project_root는 열지 않는다 (이전 워크스페이스 복원 회피).
    """
    exe, err = resolve_ide_exe(preferred_ide, ide_exe_path)
    if err or not exe:
        return None, err or "IDE 실행 파일을 찾을 수 없습니다."

    root = "" if new_window else (project_root or "").strip()
    if root and not Path(_expand(root)).is_dir():
        root = ""

    cli = resolve_ide_cli(preferred_ide, ide_cli_path, ide_exe_path)
    new_flag = ["--new-window"] if new_window else []
    use_shell = False
    cmd: list[str]
    if new_window and cli and cli.lower().endswith((".cmd", ".bat")):
        # CLI로 --new-window만 (폴더 없음 → 기본 화면)
        cmd = [cli, "--new-window"]
        use_shell = True
    elif cli and cli.lower().endswith((".cmd", ".bat")) and root:
        # ponytail: cmd 래퍼는 shell로 — GUI exe에 폴더 인자 직접 전달이 더 단순할 때도 있음
        cmd = [cli, *new_flag, root]
        use_shell = True
    elif root:
        cmd = [exe, *new_flag, root]
    else:
        cmd = [exe, *new_flag] if new_flag else [exe]

    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=root or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            shell=use_shell,
        )
        return int(proc.pid), ""
    except OSError as exc:
        return None, str(exc)


def open_folder_in_ide(
    preferred_ide: str,
    folder: str,
    *,
    ide_exe_path: str = "",
    ide_cli_path: str = "",
    new_window: bool = True,
    reuse_window: bool = False,
) -> tuple[int | None, str]:
    """이미 IDE가 떠 있어도 폴더를 (새 창으로) 연다. (pid, error).

    Cursor/VS Code: `cli [--new-window] <folder>`
    """
    root = Path(_expand((folder or "").strip())).expanduser()
    if not root.is_dir():
        return None, f"not a directory: {folder}"
    root_s = str(root.resolve())

    exe, err = resolve_ide_exe(preferred_ide, ide_exe_path)
    if err or not exe:
        return None, err or "IDE 실행 파일을 찾을 수 없습니다."
    cli = resolve_ide_cli(preferred_ide, ide_cli_path, ide_exe_path)

    use_shell = False
    ide_id = (preferred_ide or "").strip().lower()
    supports_reuse = ide_id in ("cursor", "vscode")
    if cli and cli.lower().endswith((".cmd", ".bat")):
        cmd = [cli]
        if new_window:
            cmd.append("--new-window")
        elif reuse_window and supports_reuse:
            cmd.append("--reuse-window")
        cmd.append(root_s)
        use_shell = True
    else:
        cmd = [exe]
        if new_window:
            cmd.append("--new-window")
        elif reuse_window and supports_reuse:
            cmd.append("--reuse-window")
        cmd.append(root_s)

    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=root_s,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            shell=use_shell,
        )
        return int(proc.pid), ""
    except OSError as exc:
        return None, str(exc)


def open_file_in_ide(
    preferred_ide: str,
    file_path: str,
    *,
    ide_exe_path: str = "",
    ide_cli_path: str = "",
    line: int = 1,
    column: int = 1,
    reuse_window: bool = True,
) -> tuple[bool, str]:
    """파일을 IDE 에디터 탭으로 연다. (ok, error).

    Cursor/VS Code: `cli [-r] -g path:line[:column]`
    """
    path = Path(_expand((file_path or "").strip())).expanduser()
    if not path.is_file():
        return False, f"not a file: {file_path}"
    path_s = str(path.resolve())
    ln = max(1, int(line or 1))
    col = max(1, int(column or 1))
    goto = f"{path_s}:{ln}:{col}"

    exe, err = resolve_ide_exe(preferred_ide, ide_exe_path)
    if err or not exe:
        return False, err or "IDE 실행 파일을 찾을 수 없습니다."
    cli = resolve_ide_cli(preferred_ide, ide_cli_path, ide_exe_path)
    ide_id = (preferred_ide or "").strip().lower()
    supports_goto = ide_id in ("cursor", "vscode")

    use_shell = False
    if supports_goto and cli:
        cmd = [cli]
        if reuse_window:
            cmd.append("--reuse-window")
        cmd.extend(["--goto", goto])
        use_shell = cli.lower().endswith((".cmd", ".bat"))
    elif supports_goto:
        cmd = [exe]
        if reuse_window:
            cmd.append("--reuse-window")
        cmd.extend(["--goto", goto])
    else:
        # ponytail: JetBrains 등은 파일 경로만 전달 — 줄 이동은 CLI마다 다름
        cmd = [cli or exe, path_s]
        use_shell = bool(cli) and cli.lower().endswith((".cmd", ".bat"))

    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            shell=use_shell,
        )
        return True, ""
    except OSError as exc:
        return False, str(exc)


def wait_for_ide_window(
    preferred_ide: str,
    *,
    ide_exe_path: str = "",
    timeout_sec: float = 12.0,
) -> tuple[int | None, int | None]:
    """실행 직후 HWND 확보. (hwnd, pid)."""
    deadline = time.monotonic() + timeout_sec
    last_pid: int | None = None
    while time.monotonic() < deadline:
        hwnd, pid = find_running_ide(preferred_ide, ide_exe_path)
        if pid:
            last_pid = pid
        if hwnd:
            return hwnd, pid
        time.sleep(0.35)
    return None, last_pid


def open_install_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    try:
        import webbrowser

        return bool(webbrowser.open(url))
    except Exception:
        return False


if __name__ == "__main__":
    # 최소 자가 점검
    cur = get_ide_spec("cursor")
    assert cur is not None and cur.name == "Cursor"
    vs = get_ide_spec("vscode")
    assert vs is not None and any("codeBin" in x for x in vs.which_exclude)
    exe, _err = resolve_ide_exe("cursor")
    print("cursor exe:", exe or "(missing)")
    print("vscode installed:", is_ide_installed("vscode"))
    print("ide_launcher ok")
