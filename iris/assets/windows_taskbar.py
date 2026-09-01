"""Windows 작업표시줄 아이콘 — AppUserModelID + shortcut 등록/복구.

thin launcher(dist/IRIS.exe) → pythonw.exe -m iris 이므로 실행 중 프로세스는 pythonw다.
Windows는 AppUserModelID + Start Menu / 고정(pin) .lnk 의 아이콘·ID로 작업표시줄을 그린다.

「작업 표시줄에 고정」 시 pythonw.exe 링크가 생기면 Python 로고로 돌아간다 —
IRIS 소유 .lnk 만 골라 dist\\IRIS.exe + AppUserModelID + iris_icon 으로 복구한다.
Chrome/Cursor/Explorer 등 타 앱 .lnk 는 절대 수정하지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from iris.assets.branding import APP_USER_MODEL_ID, app_icon_path

_START_MENU_NAME = "IRIS.lnk"
# Microsoft 권장: Company.Product.SubProduct — 타 앱과 절대 충돌하지 않게 IRIS 전용
_FOREIGN_EXE_NAMES = frozenset(
    {
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "opera.exe",
        "brave.exe",
        "cursor.exe",
        "code.exe",
        "devenv.exe",
        "explorer.exe",
        "windowsterminal.exe",
        "wt.exe",
        "powershell.exe",
        "cmd.exe",
        "notepad.exe",
        "dllhost.exe",
    }
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _launcher_exe(root: Path | None = None) -> Path:
    root = root or _project_root()
    return root / "dist" / "IRIS.exe"


def _start_menu_lnk() -> Path:
    start = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
    return start / _START_MENU_NAME


def _pinned_taskbar_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / "AppData/Roaming/Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar",
    ]


def apply_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def _read_shell_link(lnk_path: Path) -> dict[str, str]:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    out = {"target": "", "args": "", "app_id": ""}
    if not lnk_path.is_file():
        return out
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLinkW,
    )
    persist = link.QueryInterface(pythoncom.IID_IPersistFile)
    persist.Load(str(lnk_path.resolve()))
    try:
        out["target"] = (link.GetPath(shell.SLGP_UNCPRIORITY)[0] or "").strip()
    except Exception:
        pass
    try:
        out["args"] = (link.GetArguments() or "").strip()
    except Exception:
        pass
    try:
        store = link.QueryInterface(propsys.IID_IPropertyStore)
        pv = store.GetValue(pscon.PKEY_AppUserModel_ID)
        out["app_id"] = (pv.GetValue() or "").strip() if pv else ""
    except Exception:
        pass
    return out


def _is_blocked_foreign_target(target: str) -> bool:
    name = Path((target or "").strip()).name.lower()
    return bool(name) and name in _FOREIGN_EXE_NAMES


def _args_launch_iris_module(args: str) -> bool:
    parts = (args or "").lower().split()
    for i, part in enumerate(parts):
        if part == "-m" and i + 1 < len(parts):
            mod = parts[i + 1]
            if mod == "iris" or mod.startswith("iris."):
                return True
    return False


def _is_iris_owned_shortcut(info: dict[str, str], *, root: Path) -> bool:
    """IRIS 관련 .lnk 만 True — 타 앱은 False (수정 금지)."""
    target = (info.get("target") or "").strip()
    if not target:
        return False
    if _is_blocked_foreign_target(target):
        return False

    target_l = target.lower().replace("\\", "/")
    root_l = str(root.resolve()).lower().replace("\\", "/")
    exe_name = Path(target).name.lower()

    if exe_name == "iris.exe" and root_l in target_l:
        return True

    if exe_name in ("pythonw.exe", "python.exe"):
        if not _args_launch_iris_module(info.get("args") or ""):
            return False
        # 프로젝트 .venv pythonw 만 — 다른 Python 앱 pin 과 분리
        return root_l in target_l

    return False


def _write_shell_link(
    lnk_path: Path,
    *,
    target: Path,
    work_dir: Path,
    icon_path: Path,
    description: str,
    arguments: str = "",
) -> None:
    import pythoncom
    from win32com.shell import shell

    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLinkW,
    )
    link.SetPath(str(target.resolve()))
    link.SetWorkingDirectory(str(work_dir.resolve()))
    link.SetDescription(description)
    if arguments:
        link.SetArguments(arguments)
    link.SetIconLocation(str(icon_path.resolve()), 0)
    persist = link.QueryInterface(pythoncom.IID_IPersistFile)
    persist.Save(str(lnk_path.resolve()), 0)


def _set_lnk_app_id(lnk_path: Path, app_id: str) -> None:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    if not lnk_path.is_file():
        return
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_IShellLinkW,
    )
    persist = link.QueryInterface(pythoncom.IID_IPersistFile)
    persist.Load(str(lnk_path.resolve()))
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(app_id))
    store.Commit()
    persist.Save(str(lnk_path.resolve()), 0)


def _canonical_launch_target(root: Path) -> tuple[Path, Path, str]:
    """(target_exe, work_dir, arguments) — 고정(pin)·시작메뉴는 IRIS.exe 우선."""
    exe = _launcher_exe(root)
    if exe.is_file():
        return exe, root, ""
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    if pyw.is_file():
        return pyw, root, "-m iris"
    return Path(sys.executable), root, "-m iris"


def write_branded_shortcut(
    lnk_path: Path,
    *,
    target: Path | None = None,
    arguments: str = "",
    work_dir: Path | None = None,
    icon_path: Path | None = None,
    app_id: str = APP_USER_MODEL_ID,
    description: str = "IRIS",
) -> None:
    """AppUserModelID + iris_icon 이 들어간 .lnk 생성/갱신."""
    if sys.platform != "win32":
        return
    root = _project_root()
    canon_target, canon_work, canon_args = _canonical_launch_target(root)
    target = target or canon_target
    arguments = arguments if target != canon_target else canon_args
    work_dir = work_dir or canon_work
    icon = icon_path or app_icon_path()
    if not icon.is_file():
        return
    try:
        _write_shell_link(
            lnk_path,
            target=target,
            work_dir=work_dir,
            icon_path=icon,
            description=description,
            arguments=arguments,
        )
        _set_lnk_app_id(lnk_path, app_id)
    except Exception:
        pass


def repair_pinned_taskbar_shortcuts() -> int:
    """작업표시줄에 고정된 IRIS .lnk 만 IRIS.exe + AppID + 아이콘으로 복구."""
    if sys.platform != "win32":
        return 0
    root = _project_root()
    icon = app_icon_path()
    if not icon.is_file():
        return 0
    target, work_dir, arguments = _canonical_launch_target(root)
    repaired = 0
    for folder in _pinned_taskbar_dirs():
        if not folder.is_dir():
            continue
        for lnk in folder.glob("*.lnk"):
            try:
                info = _read_shell_link(lnk)
            except Exception:
                continue
            if not _is_iris_owned_shortcut(info, root=root):
                continue
            # 이미 올바르면 스킵
            cur_target = (info.get("target") or "").strip().lower()
            if (
                cur_target == str(target.resolve()).lower()
                and (info.get("app_id") or "").strip() == APP_USER_MODEL_ID
                and (info.get("args") or "").strip() == arguments
            ):
                continue
            try:
                _write_shell_link(
                    lnk,
                    target=target,
                    work_dir=work_dir,
                    icon_path=icon,
                    description="IRIS",
                    arguments=arguments,
                )
                _set_lnk_app_id(lnk, APP_USER_MODEL_ID)
                repaired += 1
            except Exception:
                continue
    return repaired


def ensure_windows_taskbar_branding() -> None:
    """QApplication 전 — AppID + Start Menu + 고정(pin) shortcut 복구."""
    apply_windows_app_id()
    if sys.platform != "win32":
        return
    write_branded_shortcut(_start_menu_lnk())
    repair_pinned_taskbar_shortcuts()


def install_all_shortcuts() -> list[Path]:
    """build/install — Desktop / StartMenu / 프로젝트 + pin 복구."""
    if sys.platform != "win32":
        return []
    root = _project_root()
    icon = app_icon_path()
    paths = [
        Path.home() / "Desktop" / _START_MENU_NAME,
        _start_menu_lnk(),
        root / _START_MENU_NAME,
    ]
    for p in paths:
        write_branded_shortcut(p, icon_path=icon)
    repair_pinned_taskbar_shortcuts()
    return paths


def _self_check() -> None:
    root = _project_root()
    fake = {
        "target": r"C:\Windows\System32\cmd.exe",
        "args": "",
        "app_id": APP_USER_MODEL_ID,
    }
    assert not _is_iris_owned_shortcut(fake, root=root), "must not touch cmd"
    fake2 = {
        "target": str(_launcher_exe(root)),
        "args": "",
        "app_id": "",
    }
    assert _is_iris_owned_shortcut(fake2, root=root), "iris.exe must match"
    ensure_windows_taskbar_branding()
    assert _start_menu_lnk().is_file()
    print("windows_taskbar ok", APP_USER_MODEL_ID, "pinned_dirs", len(_pinned_taskbar_dirs()))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        for p in install_all_shortcuts():
            print("shortcut", p)
        n = repair_pinned_taskbar_shortcuts()
        print("pinned_repaired", n)
    elif len(sys.argv) > 1 and sys.argv[1] == "repair-pinned":
        print("pinned_repaired", repair_pinned_taskbar_shortcuts())
    else:
        _self_check()
