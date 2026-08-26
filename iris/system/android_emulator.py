"""Android 에뮬레이터 — 프로젝트 폴더에 AVD·데이터 저장."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANDROID_EMU_DIR = PROJECT_ROOT / "android-emulator"
AVD_HOME = ANDROID_EMU_DIR / "avd"
DATA_DIR = ANDROID_EMU_DIR / "data"
AVD_NAME = "IrisLight_Pixel"
_SYSTEM_IMAGE = "system-images;android-36;google_apis_playstore_ps16k;x86_64"
_DEVICE_ID = "pixel_9a"
# 포인터 .ini 의 target= 값. _SYSTEM_IMAGE 의 API 레벨과 같아야 한다.
_AVD_TARGET = "android-36"
_DATA_PARTITION_SIZE = "32G"
_SDCARD_SIZE = "2048M"
# ponytail: 신규 AVD는 userdata 32G 생성이라 여유가 필요. 기존 이미지가 있으면 완화.
_MIN_FREE_BYTES_FRESH = 40 * 1024 * 1024 * 1024
_MIN_FREE_BYTES_EXISTING = 2 * 1024 * 1024 * 1024
# adb emu kill 후 정상 종료를 기다리는 시간. 강제 종료는 창 잔상을 남긴다.
_GRACEFUL_EXIT_S = 12.0
_KEYBOARD_HINT_KO = (
    "한글은 에뮬 화면 키보드(IME) 사용. PC 키보드는 영문·특수키(hw.keyboard)용."
)

_launch_lock = threading.Lock()
_launch_in_progress = False
_launch_log_handle: object | None = None
# 우리가 띄운 emulator.exe PID. cmdline이 비어 있는 자식(고스트 창) 추적용.
_launched_pids: set[int] = set()
_launched_headless = False
# ponytail: 콘솔 깜빡이는 CIM 스캔 금지 → psutil+캐시.
_process_scan_cache: tuple[float, list[tuple[str, int, int, str]]] = (0.0, [])
_PROCESS_SCAN_TTL_S = 1.5
# GPU: angle/swiftshader는 이 PC(RTX 50xx + Emulator 36)에서 SwiftShader로
# 떨어져 검게 남음. host(GLES)가 실제 표시된다. CREATE_NO_WINDOW는 SW_HIDE 없이만.
_GPU_MODE = "host"


def _sdk_root() -> Path:
    for key in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        val = os.environ.get(key, "").strip()
        if val:
            return Path(val)
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidate = Path(local) / "Android" / "Sdk"
        if candidate.is_dir():
            return candidate
    home_sdk = Path.home() / "Android" / "Sdk"
    if home_sdk.is_dir():
        return home_sdk
    # 기대 경로만 반환(존재하지 않을 수 있음) — 하드코딩 사용자 경로 금지
    if local:
        return Path(local) / "Android" / "Sdk"
    return home_sdk


def emulator_exe() -> Path:
    return _sdk_root() / "emulator" / ("emulator.exe" if sys.platform == "win32" else "emulator")


def adb_exe() -> Path:
    return _sdk_root() / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb")


def _no_window_kwargs(**extra: object) -> dict:
    """adb/taskkill/avdmanager — 콘솔 창이 안 뜨게.

    GUI 에뮬 기동에는 쓰지 말 것 — CREATE_NO_WINDOW/SW_HIDE 가
    UpdateLayeredWindowIndirect 실패(검은 화면)를 낸다.
    DETACHED + Cascadia/PseudoConsole 표면 숨김.
    """
    from iris.system.win_subprocess import no_window_kwargs

    return no_window_kwargs(**extra)  # type: ignore[arg-type]


def _capture_output(cmd: list[str], *, timeout: float = 10.0) -> str:
    """콘솔 창 없이 stdout 캡처. 실패 시 빈 문자열."""
    try:
        return subprocess.check_output(
            cmd,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            **_no_window_kwargs(),
        )
    except (subprocess.SubprocessError, OSError):
        return ""


def avdmanager_exe() -> Path:
    sdk = _sdk_root()
    name = "avdmanager.bat" if sys.platform == "win32" else "avdmanager"
    return sdk / "cmdline-tools" / "latest" / "bin" / name


def avd_config_path() -> Path:
    return AVD_HOME / f"{AVD_NAME}.avd" / "config.ini"


def launch_log_path() -> Path:
    return DATA_DIR / "emulator_launch.log"


def _has_existing_userdata() -> bool:
    candidates = [
        AVD_HOME / f"{AVD_NAME}.avd" / "userdata-qemu.img",
        AVD_HOME / f"{AVD_NAME}.avd" / "userdata-qemu.img.qcow2",
        DATA_DIR / "userdata-qemu.img",
        DATA_DIR / "userdata-qemu.img.qcow2",
    ]
    for p in candidates:
        try:
            if p.is_file() and p.stat().st_size > 50 * 1024 * 1024:
                return True
        except OSError:
            continue
    return False


def _running_emulator_serials() -> list[str]:
    adb = adb_exe()
    if not adb.is_file():
        return []
    devices = _capture_output([str(adb), "devices"], timeout=10.0)
    serials: list[str] = []
    for line in devices.splitlines():
        line = line.strip()
        if not line.startswith("emulator-"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def _serial_avd_name(serial: str) -> str:
    adb = adb_exe()
    if not adb.is_file():
        return ""
    out = _capture_output([str(adb), "-s", serial, "emu", "avd", "name"], timeout=10.0)
    # adb emu avd name → "IrisLight_Pixel\nOK"
    for line in out.splitlines():
        name = line.strip()
        if name and name.upper() != "OK":
            return name
    return ""


def _matching_emulator_serials() -> list[str]:
    return [serial for serial in _running_emulator_serials() if _serial_avd_name(serial) == AVD_NAME]


def _pids_alive(pids: set[int]) -> bool:
    for pid in pids:
        if pid <= 0:
            continue
        try:
            os.kill(pid, 0)
        except (OSError, SystemError):
            continue
        return True
    return False


def _scan_processes(*, force: bool = False) -> list[tuple[str, int, int, str]]:
    """(name, pid, ppid, cmdline) — 에뮬/qemu만 (캐시).

    콘솔 서브프로세스 스캔 금지 — 표준 psutil만 사용.
    """
    global _process_scan_cache
    now = time.time()
    if not force and now - _process_scan_cache[0] < _PROCESS_SCAN_TTL_S:
        return _process_scan_cache[1]

    rows: list[tuple[str, int, int, str]] = []
    try:
        import psutil
    except ImportError:
        _process_scan_cache = (now, [])
        return []

    try:
        for proc in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
            try:
                info = proc.info
                name = str(info.get("name") or "")
                if not _is_emulator_binary(name):
                    continue
                pid = int(info["pid"])
                ppid = int(info.get("ppid") or 0)
                raw_cmd = info.get("cmdline") or []
                if isinstance(raw_cmd, (list, tuple)):
                    cmdline = " ".join(str(p) for p in raw_cmd)
                else:
                    cmdline = str(raw_cmd)
                rows.append((name, pid, ppid, cmdline))
            except (psutil.Error, TypeError, ValueError, KeyError):
                continue
    except Exception:
        rows = []

    _process_scan_cache = (now, rows)
    return rows


def _is_emulator_binary(name: str) -> bool:
    lowered = name.lower()
    return "emulator" in lowered or "qemu-system" in lowered


def _cmdline_is_project_avd(cmdline: str) -> bool:
    """프로젝트 AVD를 가리키는 커맨드라인인가.

    `-avd IrisLight_Pixel` 뿐 아니라 qemu 단계에서 남는 AVD 경로/datadir도 인정한다.
    launcher만 매칭하면 UI(qemu) 프로세스가 살아남아 빈 창이 남는다.
    """
    if not cmdline:
        return False
    norm = cmdline.replace("\\", "/").lower()
    markers = (
        f"-avd {AVD_NAME}".lower(),
        f"{AVD_NAME}.avd".lower(),
        AVD_NAME.lower(),
        str(DATA_DIR).replace("\\", "/").lower(),
    )
    return any(m in norm for m in markers)


def _descendant_pids(procs: list[tuple[str, int, int, str]], roots: set[int]) -> set[int]:
    """roots와 모든 자손 PID. Windows는 부모가 죽어도 ppid가 남아 추적된다."""
    children: dict[int, list[int]] = {}
    for _name, pid, ppid, _cmd in procs:
        children.setdefault(ppid, []).append(pid)
    seen: set[int] = set()
    stack = [p for p in roots]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, []))
    return seen


def _emulator_rows(procs: list[tuple[str, int, int, str]]) -> list[tuple[str, int, str]]:
    tracked = _descendant_pids(procs, set(_launched_pids)) if _launched_pids else set()
    rows: list[tuple[str, int, str]] = []
    for name, pid, _ppid, cmdline in procs:
        if not _is_emulator_binary(name):
            continue
        if _cmdline_is_project_avd(cmdline) or pid in tracked:
            rows.append((name, pid, cmdline))
    return rows


def _list_emulator_processes() -> list[tuple[str, int, str]]:
    return _emulator_rows(_scan_processes())


def is_emulator_headless() -> bool:
    if _launch_in_progress or _pids_alive(_launched_pids):
        return bool(_launched_headless)
    for name, _pid, cmdline in _list_emulator_processes():
        lowered = f"{name} {cmdline}".lower()
        if "-no-window" in lowered or "headless" in lowered:
            return True
    return False


def is_emulator_running() -> bool:
    """기동 여부 — adb/추적 PID 우선 (폴링 핫패스에서 PowerShell 최소화)."""
    if _launch_in_progress:
        return True
    if _matching_emulator_serials():
        return True
    if _pids_alive(_launched_pids):
        return True
    return bool(_list_emulator_processes())


def is_emulator_process_up() -> bool:
    """adb 없이 프로세스/추적 PID만 — get_state UI 핫패스용."""
    if _launch_in_progress:
        return True
    if _pids_alive(_launched_pids):
        return True
    return bool(_list_emulator_processes())


def prepare_emulator() -> tuple[bool, str]:
    """IRIS 기동 시 AVD·경로·디스크·adb 를 점검/수리한다.

    에뮬 GUI를 띄우지 않는다. 콘솔 창 없이 adb start-server만 워밍한다.
    Returns (ok, detail) — detail은 알림 한 줄용.
    """
    exe = emulator_exe()
    if not exe.is_file():
        return False, f"emulator 없음 ({exe})"
    adb = adb_exe()
    if not adb.is_file():
        return False, f"adb 없음 ({adb})"
    try:
        _ensure_emulator_disk_space()
    except OSError as exc:
        return False, str(exc)

    cfg = avd_config_path()
    if not cfg.is_file():
        mgr = avdmanager_exe()
        if mgr.is_file():
            _warm_adb_server()
            return True, f"실행 가능 (AVD {AVD_NAME} 자동 생성 가능)"
        return False, f"AVD·avdmanager 없음 ({mgr})"

    image = system_image_dir()
    if not image.is_dir():
        return False, (
            f"시스템 이미지 없음 — Android Studio SDK Manager에서 "
            f"'{_SYSTEM_IMAGE}' 설치 필요"
        )

    notes: list[str] = []
    if repair_avd_pointer():
        notes.append("경로 복구")
    dropped = _drop_foreign_runtime_artifacts()
    if dropped:
        notes.append(f"이물질 {len(dropped)}개 정리")
    try:
        _patch_avd_storage(cfg)
        _invalidate_stale_gpu_runtime(cfg)
    except OSError as exc:
        return False, f"AVD 설정 패치 실패: {exc}"
    _warm_adb_server()
    detail = f"실행 가능 (AVD {AVD_NAME})"
    if notes:
        detail = f"{detail} · {' · '.join(notes)}"
    return True, detail


def is_emulator_available() -> tuple[bool, str]:
    """기동 가능 여부 — prepare_emulator와 동일(경로 수리 포함)."""
    return prepare_emulator()


def _warm_adb_server() -> None:
    """adb 서버를 콘솔 없이 미리 띄워 이후 폴링 시 창 깜빡임을 줄인다."""
    adb = adb_exe()
    if not adb.is_file():
        return
    _capture_output([str(adb), "start-server"], timeout=15.0)


def _emulator_env() -> dict[str, str]:
    env = os.environ.copy()
    env["ANDROID_AVD_HOME"] = str(AVD_HOME)
    env["ANDROID_SDK_ROOT"] = str(_sdk_root())
    env["ANDROID_HOME"] = str(_sdk_root())
    # ponytail: crash-service 콘솔 플래시 완화 (없으면 무시)
    env.setdefault("ANDROID_EMU_DISABLE_CRASH_REPORTING", "1")
    return env


# emulator.exe 가 띄우는 CUI 헬퍼 — Win11에선 ConsoleWindowClass가 아니라
# PseudoConsoleWindow(앱 PID) + Cascadia(Windows Terminal)로 뜬다.
_CONSOLE_HELPER_NAMES = frozenset(
    {
        "netsimd.exe",
        "netsim.exe",
        "crashpad_handler.exe",
        "emulator-check.exe",
        "qemu-system-x86_64.exe",
        "qemu-system-aarch64.exe",
        "emulator.exe",
    }
)
# classic conhost / Win11 ConPTY / Windows Terminal 호스트
_CONSOLE_SURFACE_CLASSES = frozenset(
    {
        "ConsoleWindowClass",
        "PseudoConsoleWindow",
        "CASCADIA_HOSTING_WINDOW_CLASS",
    }
)
# Cascadia 탭 제목 = 호스팅 중인 exe 경로 (실측)
_CONSOLE_TITLE_MARKERS = (
    "\\emulator\\netsimd",
    "\\emulator\\crashpad_handler",
    "\\emulator\\emulator.exe",
    "\\emulator\\emulator-check",
    "\\emulator\\qemu\\",
)


def _gui_launch_creationflags() -> int:
    """에뮬 GUI용 CreateProcess 플래그.

    CREATE_NO_WINDOW 금지 — 이 플래그가 있으면 Qt 레이어드 창이
    UpdateLayeredWindowIndirect 실패로 검은 화면이 된다 (실측 로그 확인).
    DETACHED|+NEW_GROUP 만으로 부모 콘솔과 분리하고, 뜨는 터미널 표면은
    PseudoConsole/Cascadia 제목·헬퍼 PID로 숨긴다.
    """
    if sys.platform != "win32":
        return 0
    flags = int(getattr(subprocess, "DETACHED_PROCESS", 0))
    flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return flags


def _is_emulator_console_title(title: str) -> bool:
    """Windows Terminal 탭 제목이 SDK emulator 헬퍼 경로인지."""
    if not title:
        return False
    lowered = title.replace("/", "\\").lower()
    return any(marker in lowered for marker in _CONSOLE_TITLE_MARKERS)


def _hide_emulator_console_surfaces(pids: set[int]) -> int:
    """에뮬 CUI 터미널만 SW_HIDE — Qt 폰 화면 창은 건드리지 않음.

    Win11 실측: qemu/crashpad/netsimd 콘솔은 ConsoleWindowClass가 아니라
    PseudoConsoleWindow(프로세스 PID)와 CASCADIA_HOSTING_WINDOW_CLASS
    (Windows Terminal, 제목=exe 경로)다. 예전 PID+ConsoleWindowClass만
    보면 창이 그대로 남는다.
    """
    if sys.platform != "win32":
        return 0
    if not pids and not _CONSOLE_TITLE_MARKERS:
        return 0
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return 0

    user32 = ctypes.windll.user32
    hidden = 0
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @WNDENUMPROC
    def _each(hwnd: int, _lp: int) -> bool:
        nonlocal hidden
        if not user32.IsWindowVisible(hwnd):
            return True
        cls_buf = ctypes.create_unicode_buffer(256)
        if user32.GetClassNameW(hwnd, cls_buf, 256) <= 0:
            return True
        if cls_buf.value not in _CONSOLE_SURFACE_CLASSES:
            return True
        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title_buf, 512)
        title = title_buf.value
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_i = int(pid.value)
        # Cascadia: WT PID라 트리에 없음 → 제목(호스팅 exe 경로)으로만 판별
        if cls_buf.value == "CASCADIA_HOSTING_WINDOW_CLASS":
            if not _is_emulator_console_title(title):
                return True
        elif pid_i not in pids and not _is_emulator_console_title(title):
            return True
        user32.ShowWindow(hwnd, 0)  # SW_HIDE
        hidden += 1
        return True

    try:
        user32.EnumWindows(_each, 0)
    except Exception:
        return hidden
    return hidden


def _pids_for_console_hide(root_pid: int) -> set[int]:
    """에뮬 트리 + netsimd/qemu/crashpad 등 헬퍼 PID."""
    pids = {root_pid} if root_pid > 0 else set()
    try:
        import psutil
    except ImportError:
        return pids
    try:
        if root_pid > 0:
            pids |= {c.pid for c in psutil.Process(root_pid).children(recursive=True)}
    except (psutil.Error, OSError):
        pass
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            name = str(proc.info.get("name") or "").lower()
            if name in _CONSOLE_HELPER_NAMES:
                pids.add(int(proc.info["pid"]))
    except (psutil.Error, TypeError, ValueError):
        pass
    return pids


def _schedule_console_hide(root_pid: int) -> None:
    """netsimd/qemu Cascadia·PseudoConsole — 부팅(~2분) 동안 반복 숨김."""

    def _run() -> None:
        # full startup toast 구간까지 netsimd/Cascadia 가 늦게 뜰 수 있다.
        deadline = time.time() + 120.0
        while time.time() < deadline:
            _hide_emulator_console_surfaces(_pids_for_console_hide(root_pid))
            time.sleep(0.35)

    threading.Thread(target=_run, daemon=True, name="iris-emu-hide-console").start()


def _patch_avd_storage(cfg: Path) -> None:
    if not cfg.is_file():
        return
    lines = cfg.read_text(encoding="utf-8").splitlines()
    # hw.keyboard=yes: PC 키보드. GPU: host (angle/swiftshader는 이 PC에서 검정).
    patches = {
        "disk.dataPartition.size": _DATA_PARTITION_SIZE,
        "sdcard.size": _SDCARD_SIZE,
        "hw.ramSize": "4096",
        "hw.keyboard": "yes",
        "hw.gpu.enabled": "yes",
        "hw.gpu.mode": _GPU_MODE,
    }
    seen = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in patches:
            out.append(f"{key}={patches[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in patches.items():
        if key not in seen:
            out.append(f"{key}={val}")
    cfg.write_text("\n".join(out) + "\n", encoding="utf-8")
    qemu = cfg.with_name("hardware-qemu.ini")
    if qemu.is_file():
        q_patches = {
            "hw.keyboard": "hw.keyboard = true",
            "hw.gpu.enabled": "hw.gpu.enabled = true",
            "hw.gpu.mode": f"hw.gpu.mode = {_GPU_MODE}",
        }
        q_lines = qemu.read_text(encoding="utf-8").splitlines()
        q_out: list[str] = []
        q_seen: set[str] = set()
        for line in q_lines:
            stripped = line.strip()
            matched: str | None = None
            for key in q_patches:
                if not stripped.startswith(key):
                    continue
                if key == "hw.keyboard" and (
                    "charmap" in stripped or "lid" in stripped
                ):
                    continue
                matched = key
                break
            if matched:
                if matched not in q_seen:
                    q_out.append(q_patches[matched])
                    q_seen.add(matched)
                continue
            q_out.append(line)
        for key, val in q_patches.items():
            if key not in q_seen:
                q_out.append(val)
        qemu.write_text("\n".join(q_out) + "\n", encoding="utf-8")


def _ensure_emulator_disk_space() -> None:
    """Fail early with a readable message instead of spawning then exiting."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(DATA_DIR).free
    need = _MIN_FREE_BYTES_EXISTING if _has_existing_userdata() else _MIN_FREE_BYTES_FRESH
    if free < need:
        need_gb = need / (1024**3)
        have_gb = free / (1024**3)
        kind = "기존 AVD" if _has_existing_userdata() else "신규 AVD"
        raise OSError(
            f"에뮬레이터 디스크 공간 부족({kind}): 필요 약 {need_gb:.1f}GB, 현재 {have_gb:.1f}GB"
        )


def avd_pointer_path() -> Path:
    """AVD_HOME/<이름>.ini — 에뮬레이터가 .avd 폴더를 찾는 포인터."""
    return AVD_HOME / f"{AVD_NAME}.ini"


def system_image_dir() -> Path:
    """config.ini 가 요구하는 시스템 이미지 경로."""
    return _sdk_root() / Path(*_SYSTEM_IMAGE.replace(";", "/").split("/"))


def repair_avd_pointer() -> bool:
    """포인터 .ini 의 path 를 이 PC 기준으로 다시 쓴다.

    저장소에 커밋된 `IrisLight_Pixel.ini` 에는 만든 사람 PC의 절대경로가
    박혀 있다. 다른 PC에서 clone 하면 에뮬레이터가 config.ini 를 못 읽고
    기본값(arm)으로 떨어져서 이렇게 죽는다:

        CPU Architecture 'arm' is not supported by the QEMU2 emulator

    원인이 경로라는 걸 알 방법이 메시지에 없다. 매 기동 전에 고쳐 둔다.
    """
    avd_dir = AVD_HOME / f"{AVD_NAME}.avd"
    if not avd_dir.is_dir():
        return False
    pointer = avd_pointer_path()
    desired = (
        "avd.ini.encoding=UTF-8\n"
        f"path={avd_dir}\n"
        f"path.rel=avd/{AVD_NAME}.avd\n"
        f"target={_AVD_TARGET}\n"
    )
    try:
        if pointer.is_file() and pointer.read_text(encoding="utf-8") == desired:
            return False
        pointer.write_text(desired, encoding="utf-8")
    except OSError:
        return False
    return True


def _stale_runtime_artifacts() -> list[Path]:
    """다른 PC 경로가 박힌 채 굳어 버리는 런타임 산출물.

    에뮬레이터가 기동할 때마다 다시 만드는 파일들인데, 저장소에 커밋돼
    있으면 남의 SDK/AVD 경로를 그대로 물고 들어온다.
    """
    avd_dir = AVD_HOME / f"{AVD_NAME}.avd"
    names = (
        "hardware-qemu.ini",
        "emulator-user.ini",
        "quickbootChoice.ini",
        "read-snapshot.txt",
        "version_num.cache",
    )
    return [avd_dir / name for name in names if (avd_dir / name).is_file()]


def _drop_foreign_runtime_artifacts() -> list[str]:
    """이 PC 것이 아닌 경로를 담은 런타임 산출물만 지운다."""
    marker = str(_sdk_root()).lower()
    dropped: list[str] = []
    for path in _stale_runtime_artifacts():
        try:
            body = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if marker in body:
            continue  # 이 PC에서 만들어진 것 — 그대로 둔다
        try:
            path.unlink()
            dropped.append(path.name)
        except OSError:
            pass
    return dropped


def ensure_avd() -> str:
    """프로젝트 AVD가 없으면 생성하고, 경로·저장 용량을 이 PC 기준으로 맞춘다."""
    AVD_HOME.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = avd_config_path()
    if cfg.is_file():
        repair_avd_pointer()
        _drop_foreign_runtime_artifacts()
        image = system_image_dir()
        if not image.is_dir():
            raise FileNotFoundError(
                f"시스템 이미지 없음: {image}\n"
                f"Android Studio > SDK Manager 에서 '{_SYSTEM_IMAGE}' 를 설치하거나,\n"
                f"sdkmanager \"{_SYSTEM_IMAGE}\" 로 내려받으세요.\n"
                "(설치돼 있지 않으면 에뮬레이터가 arm 으로 잘못 떨어져 "
                "\"CPU Architecture 'arm' is not supported\" 로 죽습니다.)"
            )
        _patch_avd_storage(cfg)
        # hardware-qemu.ini 가 옛 gpu mode를 물고 있으면 -gpu CLI를 무시한다.
        _invalidate_stale_gpu_runtime(cfg)
        return AVD_NAME

    avd_mgr = avdmanager_exe()
    if not avd_mgr.is_file():
        raise FileNotFoundError(f"avdmanager 없음: {avd_mgr}")

    subprocess.run(
        [
            str(avd_mgr),
            "create",
            "avd",
            "-n",
            AVD_NAME,
            "-k",
            _SYSTEM_IMAGE,
            "-d",
            _DEVICE_ID,
        ],
        input="no\n",
        text=True,
        env=_emulator_env(),
        check=True,
        timeout=180,
        **_no_window_kwargs(),
    )
    _patch_avd_storage(cfg)
    _invalidate_stale_gpu_runtime(cfg)
    return AVD_NAME


def _invalidate_stale_gpu_runtime(cfg: Path) -> None:
    """config.ini GPU와 다른 hardware-qemu.ini 는 지워 재생성하게 한다.

    에뮬이 기동마다 다시 쓰므로, 옛 swiftshader 값이 남으면 host CLI보다
    우선해 검은 화면이 날 수 있다.
    """
    qemu = cfg.with_name("hardware-qemu.ini")
    if not qemu.is_file():
        return
    try:
        body = qemu.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    want = f"hw.gpu.mode = {_GPU_MODE}"
    # 공백 유무 모두 허용
    if want in body or f"hw.gpu.mode={_GPU_MODE}" in body:
        return
    try:
        qemu.unlink()
    except OSError:
        pass


def _clear_launch_flag_later() -> None:
    """기동 직후 이중 spawn 방지 — 프로세스/시리얼 보이거나 20초 후 플래그 해제."""

    def _run() -> None:
        global _launch_in_progress
        deadline = time.time() + 20
        while time.time() < deadline:
            if _list_emulator_processes() or _matching_emulator_serials():
                break
            time.sleep(0.4)
        with _launch_lock:
            _launch_in_progress = False

    threading.Thread(target=_run, daemon=True).start()


def launch_emulator(*, headless: bool = False) -> subprocess.Popen[bytes]:
    """에뮬레이터를 프로젝트 android-emulator/data 에 userdata로 실행."""
    global _launch_in_progress, _launch_log_handle, _launched_headless, _process_scan_cache

    if not emulator_exe().is_file():
        raise FileNotFoundError(f"emulator 없음: {emulator_exe()}")

    with _launch_lock:
        if _launch_in_progress:
            raise OSError("에뮬레이터 기동 중 — 잠시 후 다시 시도")
        if _list_emulator_processes() or _matching_emulator_serials():
            raise OSError(f"에뮬레이터 이미 실행 중 (AVD {AVD_NAME})")
        _launch_in_progress = True

    try:
        name = ensure_avd()
        _ensure_emulator_disk_space()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_path = launch_log_path()
        if _launch_log_handle is not None:
            try:
                _launch_log_handle.close()  # type: ignore[union-attr]
            except Exception:
                pass
        _launch_log_handle = open(log_path, "w", encoding="utf-8", errors="replace")
        cmd = [
            str(emulator_exe()),
            "-avd",
            name,
            "-datadir",
            str(DATA_DIR),
            "-gpu",
            _GPU_MODE,
            # ponytail: config.ini 패치 후 깨진 quickboot 스냅샷이 adb offline을 유발할 수 있음
            "-no-snapshot-load",
            # Vulkan host ICD + 레이어드 창 충돌 회피
            "-feature",
            "-Vulkan",
            # netsimd 웹UI 소음 축소 (터미널 표면은 _schedule_console_hide)
            "-netsim-args",
            "--no-web-ui",
        ]
        if headless:
            cmd.append("-no-window")
        _launch_log_handle.write(f"cmd: {' '.join(cmd)}\n")  # type: ignore[union-attr]
        _launch_log_handle.flush()  # type: ignore[union-attr]
        # CREATE_NO_WINDOW 금지 → UpdateLayeredWindowIndirect 실패(검은 화면).
        # DETACHED + Win11 Cascadia/PseudoConsole(제목·헬퍼 PID) 숨김.
        env = _emulator_env()
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=_launch_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=_gui_launch_creationflags(),
            close_fds=False,
        )
        _launched_pids.add(proc.pid)
        _launched_headless = bool(headless)
        _process_scan_cache = (0.0, [])
        _schedule_console_hide(proc.pid)
        _clear_launch_flag_later()
        return proc
    except Exception:
        with _launch_lock:
            _launch_in_progress = False
        raise


def restart_emulator_windowed() -> subprocess.Popen[bytes]:
    """headless/stale 프로젝트 AVD를 정리하고 창 있는 인스턴스로 다시 띄운다."""
    kill_emulator()
    deadline = time.time() + 15
    while time.time() < deadline:
        if not is_emulator_running():
            break
        time.sleep(0.5)
    return launch_emulator(headless=False)


# --- Control Surface용 안전 adb 래퍼 (임의 shell 문자열 금지) ---

_KEYEVENT_CODES: dict[str, int] = {
    "HOME": 3,
    "BACK": 4,
    "ENTER": 66,
    "APP_SWITCH": 187,
    "POWER": 26,
}

_SAFE_FILTER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.*_-")


class AdbError(RuntimeError):
    """adb 호출 실패 — Control Surface err_result 메시지로 전달."""


def adb_run(
    args: list[str],
    *,
    serial: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    """허용된 adb argv만 실행. returns (code, stdout, stderr)."""
    adb = adb_exe()
    if not adb.is_file():
        raise AdbError(f"adb 없음: {adb}")
    cmd = [str(adb)]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            # adb 출력은 UTF-8. 기본 로케일(cp949)로 읽으면 한글 UI 덤프에서 깨진다.
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_emulator_env(),
            **_no_window_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb timeout ({timeout}s): {' '.join(args)}") from exc
    except OSError as exc:
        raise AdbError(str(exc)) from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def require_serial() -> str:
    """IrisLight_Pixel에 매칭되는 online serial. 없으면 AdbError."""
    matched = _matching_emulator_serials()
    if matched:
        return matched[0]
    all_serials = _running_emulator_serials()
    if all_serials:
        raise AdbError(
            f"AVD {AVD_NAME} serial 없음 (다른 에뮬만 실행 중: {', '.join(all_serials)})"
        )
    # ponytail: CallMonitor 폴링에서 PowerShell 스캔을 돌리면 콘솔이 깜빡인다.
    if _launch_in_progress:
        raise AdbError(
            f"AVD {AVD_NAME} 기동 중 — adb device 대기 (부팅 후 다시 시도)"
        )
    raise AdbError(f"에뮬레이터 미실행 (AVD {AVD_NAME})")


def _getprop(serial: str, key: str) -> str:
    code, out, _err = adb_run(["shell", "getprop", key], serial=serial, timeout=10.0)
    if code != 0:
        return ""
    return (out or "").strip()


def is_boot_completed(serial: str | None = None) -> bool:
    ser = serial
    if not ser:
        matched = _matching_emulator_serials()
        ser = matched[0] if matched else None
    if not ser:
        return False
    return _getprop(ser, "sys.boot_completed") == "1"


def wait_for_boot(*, timeout_s: float = 180.0, poll_s: float = 2.0) -> str:
    """adb serial + sys.boot_completed=1 까지 대기. serial 반환."""
    if timeout_s < 1 or timeout_s > 600:
        raise AdbError("timeout_s must be 1..600")
    deadline = time.time() + float(timeout_s)
    last = "waiting"
    while time.time() < deadline:
        serials = _matching_emulator_serials()
        if serials:
            ser = serials[0]
            if _getprop(ser, "sys.boot_completed") == "1":
                return ser
            last = f"serial {ser} booting"
        elif _list_emulator_processes() or _launch_in_progress:
            last = "process up, waiting for adb"
        else:
            last = "no emulator process"
        time.sleep(max(0.5, float(poll_s)))
    raise AdbError(f"boot timeout ({timeout_s}s): {last}")


def read_launch_log_tail(*, lines: int = 40) -> str:
    path = launch_log_path()
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    parts = text.splitlines()
    n = max(1, min(int(lines), 200))
    return "\n".join(parts[-n:])


def emulator_status() -> dict:
    serials = _matching_emulator_serials()
    procs = _list_emulator_processes()
    serial = serials[0] if serials else None
    boot = bool(serial and is_boot_completed(serial))
    if serial and boot:
        phase = "ready"
    elif serial or procs or _launch_in_progress:
        phase = "booting" if (serial or procs) else "starting"
    else:
        phase = "stopped"
    return {
        "running": phase in ("ready", "booting", "starting"),
        "phase": phase,
        "adb_ready": bool(serial),
        "boot_completed": boot,
        "serials": list(serials),
        "serial": serial,
        "headless": is_emulator_headless() if phase != "stopped" else False,
        "avd": AVD_NAME,
        "adb": str(adb_exe()),
        "adb_ok": adb_exe().is_file(),
        "launch_log": str(launch_log_path()),
        "keyboard_hint": _KEYBOARD_HINT_KO,
    }


def emulator_status_fast() -> dict:
    """adb 프로브 없음 — get_state가 UI에서 멈춤 방지."""
    procs = _list_emulator_processes()
    if _launch_in_progress and not procs:
        phase = "starting"
    elif procs or _pids_alive(_launched_pids):
        phase = "booting"
    else:
        phase = "stopped"
    return {
        "running": phase != "stopped",
        "phase": phase,
        "adb_ready": False,
        "boot_completed": False,
        "serials": [],
        "serial": None,
        "headless": is_emulator_headless() if phase != "stopped" else False,
        "avd": AVD_NAME,
        "adb": str(adb_exe()),
        "adb_ok": adb_exe().is_file(),
        "launch_log": str(launch_log_path()),
        "keyboard_hint": _KEYBOARD_HINT_KO,
    }


def _force_kill_pid(pid: int) -> bool:
    if sys.platform == "win32":
        kill_cmd = ["taskkill", "/PID", str(pid), "/F", "/T"]
    else:
        kill_cmd = ["kill", "-9", str(pid)]
    try:
        subprocess.run(
            kill_cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **_no_window_kwargs(),
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def _kill_targets(procs: list[tuple[str, int, int, str]]) -> list[int]:
    """종료 대상 PID — 에뮬 프로세스와 그 자손 전부, 자식(깊은 것) 먼저.

    kill 중 리페어런팅으로 창 프로세스를 놓치지 않도록 트리를 먼저 스냅샷한다.
    """
    roots = {pid for _name, pid, _cmd in _emulator_rows(procs)}
    roots |= set(_launched_pids)
    if not roots:
        return []
    targets = _descendant_pids(procs, roots)
    parent_of = {pid: ppid for _n, pid, ppid, _c in procs}
    def depth(pid: int) -> int:
        d, cur, guard = 0, pid, 0
        while cur in parent_of and guard < 64:
            cur = parent_of[cur]
            if cur not in targets:
                break
            d += 1
            guard += 1
        return d
    return sorted(targets, key=depth, reverse=True)


def kill_emulator() -> bool:
    """프로젝트 AVD 인스턴스 종료 — 창(qemu UI)까지 사라진 것을 확인한다."""
    global _launch_in_progress, _launched_headless, _process_scan_cache
    killed = False
    adb = adb_exe()
    for serial in _matching_emulator_serials():
        try:
            subprocess.run(
                [str(adb), "-s", serial, "emu", "kill"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                **_no_window_kwargs(),
            )
            killed = True
        except (subprocess.SubprocessError, OSError):
            pass

    # emu kill은 비동기다. 창이 정리되기 전에 taskkill /F 하면 Qt 창 잔상이 남으므로
    # 먼저 정상 종료를 기다리고, 그래도 남은 것만 트리째 강제 종료한다.
    if killed:
        deadline = time.time() + _GRACEFUL_EXIT_S
        while time.time() < deadline:
            if not _list_emulator_processes():
                break
            time.sleep(1.0)

    for _attempt in range(3):
        procs = _scan_processes(force=True)
        targets = _kill_targets(procs)
        if not targets:
            break
        for pid in targets:
            if _force_kill_pid(pid):
                killed = True
        time.sleep(1.5)

    with _launch_lock:
        _launch_in_progress = False
    _launched_pids.clear()
    _launched_headless = False
    _process_scan_cache = (0.0, [])
    return killed


def _escape_adb_input_text(text: str) -> str:
    """adb shell input text — 공백은 %s, 일부 특수문자 이스케이프."""
    out: list[str] = []
    for ch in text:
        if ch == " ":
            out.append("%s")
        elif ch in "()<>|;&\"'\\":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("%s")  # ponytail: newline → space 취급
        else:
            out.append(ch)
    return "".join(out)


def install_apk(apk: str, *, serial: str | None = None) -> str:
    path = Path(apk).expanduser()
    if not path.is_file():
        raise AdbError(f"APK 파일 없음: {path}")
    if path.suffix.lower() != ".apk":
        raise AdbError(f"APK 확장자 필요: {path}")
    ser = serial or require_serial()
    code, out, err = adb_run(["install", "-r", str(path.resolve())], serial=ser, timeout=180.0)
    text = (out + err).strip()
    if code != 0 or "Failure" in text or "failed" in text.lower():
        raise AdbError(text or f"install failed code={code}")
    return text or "Success"


def start_app(package: str, activity: str = "", *, serial: str | None = None) -> None:
    pkg = (package or "").strip()
    if not pkg or any(c in pkg for c in " \t\n;/|&"):
        raise AdbError("invalid package")
    act = (activity or "").strip()
    if act and any(c in act for c in " \t\n;|&"):
        raise AdbError("invalid activity")
    ser = serial or require_serial()
    if act:
        component = act if "/" in act else f"{pkg}/{act}"
        code, out, err = adb_run(
            ["shell", "am", "start", "-n", component],
            serial=ser,
            timeout=30.0,
        )
    else:
        code, out, err = adb_run(
            [
                "shell",
                "monkey",
                "-p",
                pkg,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            serial=ser,
            timeout=30.0,
        )
    if code != 0:
        raise AdbError((err or out or f"start_app failed code={code}").strip())


def press_key(key: str, *, serial: str | None = None) -> None:
    code_key = (key or "").strip().upper()
    if code_key not in _KEYEVENT_CODES:
        raise AdbError(
            f"unsupported key: {key} (allowed: {', '.join(sorted(_KEYEVENT_CODES))})"
        )
    ser = serial or require_serial()
    code, out, err = adb_run(
        ["shell", "input", "keyevent", str(_KEYEVENT_CODES[code_key])],
        serial=ser,
    )
    if code != 0:
        raise AdbError((err or out or "keyevent failed").strip())


def input_text(text: str, *, serial: str | None = None) -> None:
    if text is None:
        raise AdbError("text required")
    if len(text) > 500:
        raise AdbError("text too long (max 500)")
    # 한글 등 non-ascii는 adb input text가 깨지므로 안내
    if any(ord(ch) > 127 for ch in text):
        raise AdbError(
            "non-ASCII text not supported via adb input text — " + _KEYBOARD_HINT_KO
        )
    ser = serial or require_serial()
    escaped = _escape_adb_input_text(text)
    code, out, err = adb_run(["shell", "input", "text", escaped], serial=ser)
    if code != 0:
        raise AdbError((err or out or "input text failed").strip())


def tap(x: int, y: int, *, serial: str | None = None) -> None:
    if not isinstance(x, int) or not isinstance(y, int):
        raise AdbError("x,y must be int")
    if x < 0 or y < 0 or x > 100_000 or y > 100_000:
        raise AdbError("x,y out of range")
    ser = serial or require_serial()
    code, out, err = adb_run(["shell", "input", "tap", str(x), str(y)], serial=ser)
    if code != 0:
        raise AdbError((err or out or "tap failed").strip())


def swipe(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    duration_ms: int = 300,
    serial: str | None = None,
) -> None:
    for v in (x1, y1, x2, y2):
        if not isinstance(v, int) or v < 0 or v > 100_000:
            raise AdbError("swipe coords invalid")
    dur = int(duration_ms)
    if dur < 1 or dur > 60_000:
        raise AdbError("duration_ms out of range")
    ser = serial or require_serial()
    code, out, err = adb_run(
        ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur)],
        serial=ser,
    )
    if code != 0:
        raise AdbError((err or out or "swipe failed").strip())


def screenshot(path: str = "", *, serial: str | None = None) -> str:
    ser = serial or require_serial()
    if path.strip():
        dest = Path(path).expanduser().resolve()
    else:
        dest = PROJECT_ROOT / "android-emulator" / "data" / "iris_screenshot.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    remote = "/sdcard/iris_screenshot.png"
    code, out, err = adb_run(["shell", "screencap", "-p", remote], serial=ser, timeout=30.0)
    if code != 0:
        raise AdbError((err or out or "screencap failed").strip())
    code, out, err = adb_run(["pull", remote, str(dest)], serial=ser, timeout=30.0)
    if code != 0 or not dest.is_file():
        raise AdbError((err or out or f"pull failed → {dest}").strip())
    return str(dest)


# --- UI 인식 (uiautomator) + Play 스토어 설치 ---

_PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

# 좌표 추정 대신 알려진 패키지로 Play 상세 페이지에 바로 진입한다.
APP_ALIASES: dict[str, str] = {
    "instagram": "com.instagram.android",
    "인스타": "com.instagram.android",
    "인스타그램": "com.instagram.android",
    "telegram": "org.telegram.messenger",
    "텔레그램": "org.telegram.messenger",
    "kakaotalk": "com.kakao.talk",
    "카카오톡": "com.kakao.talk",
    "카톡": "com.kakao.talk",
    "youtube": "com.google.android.youtube",
    "유튜브": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
    "왓츠앱": "com.whatsapp",
    "discord": "com.discord",
    "디스코드": "com.discord",
    "facebook": "com.facebook.katana",
    "페이스북": "com.facebook.katana",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "line": "jp.naver.line.android",
    "라인": "jp.naver.line.android",
    "tiktok": "com.zhiliaoapp.musically",
    "틱톡": "com.zhiliaoapp.musically",
    "netflix": "com.netflix.mediaclient",
    "넷플릭스": "com.netflix.mediaclient",
    "spotify": "com.spotify.music",
    "스포티파이": "com.spotify.music",
    "chrome": "com.android.chrome",
    "크롬": "com.android.chrome",
    "settings": "com.android.settings",
    "설정": "com.android.settings",
}

_PLAY_INSTALL_TEXTS = {"install", "설치", "받기", "get"}
_PLAY_OPEN_TEXTS = {"open", "열기", "실행", "play"}
_PLAY_BUSY_TEXTS = {
    "installing",
    "설치 중",
    "설치중",
    "pending",
    "대기 중",
    "대기중",
    "downloading",
    "다운로드 중",
    "cancel",
    "취소",
    "verifying",
    "확인 중",
}
_PLAY_SIGNIN_TEXTS = {
    "sign in",
    "로그인",
    "add a google account",
    "google 계정 추가",
    "계정 추가",
    "sign in to your google account",
    "새 계정 만들기",
    "create account",
}


def resolve_package(app: str) -> str:
    """앱 별칭 또는 패키지명 → 패키지명."""
    name = (app or "").strip()
    if not name:
        raise AdbError("app/package required")
    alias = APP_ALIASES.get(name.lower())
    if alias:
        return alias
    if not _PKG_RE.match(name):
        known = ", ".join(sorted(set(APP_ALIASES)))
        raise AdbError(f"알 수 없는 앱: {app} — 패키지명을 주거나 별칭 사용 ({known})")
    return name


def is_package_installed(package: str, *, serial: str | None = None) -> bool:
    pkg = resolve_package(package)
    ser = serial or require_serial()
    code, out, _err = adb_run(["shell", "pm", "list", "packages", pkg], serial=ser, timeout=20.0)
    if code != 0:
        return False
    return any(ln.strip() == f"package:{pkg}" for ln in out.splitlines())


def ui_dump(*, serial: str | None = None, retries: int = 3) -> str:
    """현재 화면의 uiautomator XML. 좌표 추정 대신 실제 노드 bounds를 쓴다."""
    ser = serial or require_serial()
    remote = "/sdcard/iris_ui_dump.xml"
    last = ""
    for attempt in range(max(1, retries)):
        code, out, err = adb_run(
            ["shell", "uiautomator", "dump", remote], serial=ser, timeout=40.0
        )
        last = (err or out or "").strip()
        if code == 0 and "ERROR" not in last.upper():
            code, xml, err = adb_run(["shell", "cat", remote], serial=ser, timeout=40.0)
            xml = (xml or "").replace("\r\n", "\n")
            if code == 0 and "<hierarchy" in xml:
                return xml
            last = (err or xml or "cat failed").strip()
        time.sleep(1.5 * (attempt + 1))
    raise AdbError(f"uiautomator dump 실패: {last[:200]}")


def parse_ui_nodes(xml_text: str) -> list[dict]:
    """XML → [{text, desc, id, cls, clickable, bounds, cx, cy}]."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise AdbError(f"UI XML 파싱 실패: {exc}") from exc
    nodes: list[dict] = []
    for el in root.iter("node"):
        bounds = el.get("bounds") or ""
        m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", bounds)
        if not m:
            continue
        x1, y1, x2, y2 = (int(v) for v in m.groups())
        nodes.append(
            {
                "text": (el.get("text") or "").strip(),
                "desc": (el.get("content-desc") or "").strip(),
                "id": el.get("resource-id") or "",
                "cls": el.get("class") or "",
                "clickable": el.get("clickable") == "true",
                "bounds": [x1, y1, x2, y2],
                "cx": (x1 + x2) // 2,
                "cy": (y1 + y2) // 2,
            }
        )
    return nodes


def _node_labels(node: dict) -> list[str]:
    return [s.lower() for s in (node.get("text", ""), node.get("desc", "")) if s]


def find_ui_nodes(
    needle: str,
    *,
    exact: bool = False,
    serial: str | None = None,
    nodes: list[dict] | None = None,
) -> list[dict]:
    """text/content-desc가 일치(또는 포함)하는 노드. clickable 우선 정렬."""
    target = (needle or "").strip().lower()
    if not target:
        raise AdbError("text required")
    pool = nodes if nodes is not None else parse_ui_nodes(ui_dump(serial=serial))
    hits = [
        n
        for n in pool
        if any(lbl == target if exact else target in lbl for lbl in _node_labels(n))
    ]
    hits.sort(key=lambda n: (not n["clickable"], n["cy"], n["cx"]))
    return hits


def ui_texts(*, serial: str | None = None) -> list[str]:
    """화면에 보이는 텍스트/설명 목록 — 좌표를 찍기 전 상황 파악용."""
    seen: list[str] = []
    for node in parse_ui_nodes(ui_dump(serial=serial)):
        for label in (node["text"], node["desc"]):
            if label and label not in seen:
                seen.append(label)
    return seen


def tap_text(needle: str, *, exact: bool = False, serial: str | None = None) -> dict:
    ser = serial or require_serial()
    hits = find_ui_nodes(needle, exact=exact, serial=ser)
    if not hits:
        raise AdbError(f"화면에서 '{needle}' 못 찾음")
    node = hits[0]
    tap(node["cx"], node["cy"], serial=ser)
    return {"text": node["text"] or node["desc"], "x": node["cx"], "y": node["cy"]}


def open_play_page(package: str, *, serial: str | None = None) -> str:
    """market:// 딥링크로 Play 상세 페이지 직행 — 검색·좌표 탭 불필요."""
    pkg = resolve_package(package)
    ser = serial or require_serial()
    code, out, err = adb_run(
        [
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            f"'market://details?id={pkg}'",
        ],
        serial=ser,
        timeout=30.0,
    )
    text = (out + err).strip()
    if code != 0 or "Error" in text:
        raise AdbError(text or f"play page open failed code={code}")
    return pkg


def _match_labels(nodes: list[dict], wanted: set[str]) -> dict | None:
    for node in nodes:
        if any(lbl in wanted for lbl in _node_labels(node)):
            return node
    return None


def play_install(
    app: str,
    *,
    timeout_s: float = 300.0,
    serial: str | None = None,
) -> dict:
    """Play 스토어에서 앱 설치 — 딥링크 진입 후 UI 트리에서 설치 버튼을 찾아 누른다."""
    pkg = resolve_package(app)
    ser = serial or require_serial()
    timeout = max(30.0, min(float(timeout_s), 900.0))

    if is_package_installed(pkg, serial=ser):
        return {"package": pkg, "installed": True, "already_installed": True, "taps": 0}

    open_play_page(pkg, serial=ser)
    time.sleep(3.0)

    deadline = time.time() + timeout
    taps = 0
    labels: list[str] = []
    while time.time() < deadline:
        if is_package_installed(pkg, serial=ser):
            return {"package": pkg, "installed": True, "already_installed": False, "taps": taps}
        try:
            nodes = parse_ui_nodes(ui_dump(serial=ser))
        except AdbError:
            time.sleep(2.0)
            continue
        labels = [s for n in nodes for s in (n["text"], n["desc"]) if s][:40]

        if _match_labels(nodes, _PLAY_SIGNIN_TEXTS):
            raise AdbError(
                f"Play 스토어에 Google 계정 로그인이 필요합니다 (앱: {pkg}). "
                "에뮬레이터에서 로그인 후 다시 시도하세요."
            )
        if _match_labels(nodes, _PLAY_BUSY_TEXTS):
            time.sleep(4.0)
            continue
        if _match_labels(nodes, _PLAY_OPEN_TEXTS) and taps:
            time.sleep(2.0)
            continue

        button = _match_labels(nodes, _PLAY_INSTALL_TEXTS)
        if button and taps < 3:
            tap(button["cx"], button["cy"], serial=ser)
            taps += 1
            time.sleep(4.0)
            continue
        time.sleep(3.0)

    raise AdbError(
        f"설치 확인 실패 ({pkg}, taps={taps}, {timeout:.0f}s 초과). 화면 텍스트: {labels[:15]}"
    )


def logcat_tail(
    lines: int = 100,
    filter_spec: str = "",
    *,
    serial: str | None = None,
) -> list[str]:
    n = int(lines)
    if n < 1 or n > 2000:
        raise AdbError("lines must be 1..2000")
    ser = serial or require_serial()
    args = ["logcat", "-d", "-t", str(n)]
    filt = (filter_spec or "").strip()
    if filt:
        if any(c not in _SAFE_FILTER_CHARS for c in filt):
            raise AdbError("filter has unsafe characters")
        args.append(filt)
    code, out, err = adb_run(args, serial=ser, timeout=30.0)
    if code != 0:
        raise AdbError((err or out or "logcat failed").strip())
    return [ln for ln in out.splitlines() if ln.strip()]


if __name__ == "__main__":
    # dry self-check: adb 바이너리·헬퍼 (에뮬 없어도 OK)
    assert adb_exe().name.lower().startswith("adb")
    assert _escape_adb_input_text("a b") == "a%sb"
    assert _KEYEVENT_CODES["HOME"] == 3
    # adb emu avd name trailing OK
    sample = "IrisLight_Pixel\nOK"
    parsed = next(
        (ln.strip() for ln in sample.splitlines() if ln.strip() and ln.strip().upper() != "OK"),
        "",
    )
    assert parsed == "IrisLight_Pixel"
    # 종료 대상 매칭: launcher 뿐 아니라 qemu 창 프로세스도 잡아야 한다
    assert _cmdline_is_project_avd(f"emulator.exe -avd {AVD_NAME} -gpu host")
    assert _cmdline_is_project_avd(
        r"C:\Sdk\emulator\qemu\windows-x86_64\qemu-system-x86_64.exe "
        r"-android-hw C:\proj\android-emulator\avd\IrisLight_Pixel.avd\hardware-qemu.ini"
    )
    assert not _cmdline_is_project_avd("emulator.exe -avd Other_AVD")
    assert not _cmdline_is_project_avd("")
    _fake = [
        ("emulator.exe", 100, 1, f"emulator.exe -avd {AVD_NAME}"),
        ("qemu-system-x86_64.exe", 200, 100, ""),  # cmdline 없는 고스트 창
        ("chrome.exe", 300, 1, "chrome.exe"),
    ]
    assert _descendant_pids(_fake, {100}) == {100, 200}
    _launched_pids.add(100)
    try:
        assert {pid for _n, pid, _c in _emulator_rows(_fake)} == {100, 200}
        assert _kill_targets(_fake)[0] == 200  # 자식 먼저
    finally:
        _launched_pids.discard(100)
    sdk_s = str(_sdk_root())
    assert "Android" in sdk_s and "Sdk" in sdk_s
    cfg = avd_config_path()
    if cfg.is_file():
        _patch_avd_storage(cfg)
        text = cfg.read_text(encoding="utf-8")
        assert "hw.keyboard=yes" in text
        assert "hw.gpu.enabled=yes" in text
        assert f"hw.gpu.mode={_GPU_MODE}" in text
        assert "hw.gpu.mode=host" in text
    # UI 인식: bounds 파싱 → 중심 좌표, 설치 버튼 라벨 매칭
    assert resolve_package("인스타그램") == "com.instagram.android"
    assert resolve_package("org.telegram.messenger") == "org.telegram.messenger"
    try:
        resolve_package("없는앱")
        raise AssertionError("unknown app should fail")
    except AdbError:
        pass
    _xml = (
        '<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
        '<node text="" bounds="[0,0][1080,2400]" class="android.widget.FrameLayout">'
        '<node text="Instagram" content-desc="" bounds="[40,300][600,380]" class="t"/>'
        '<node text="설치" content-desc="" clickable="true" bounds="[700,300][1040,400]" class="b"/>'
        '<node text="설치됨" content-desc="" bounds="[40,500][600,560]" class="t"/>'
        "</node></hierarchy>"
    )
    _nodes = parse_ui_nodes(_xml)
    assert len(_nodes) == 4
    _btn = _match_labels(_nodes, _PLAY_INSTALL_TEXTS)
    assert _btn is not None and (_btn["cx"], _btn["cy"]) == (870, 350)  # "설치됨" 아님
    assert _match_labels(_nodes, _PLAY_SIGNIN_TEXTS) is None
    assert find_ui_nodes("instagram", nodes=_nodes)[0]["text"] == "Instagram"

    need = _MIN_FREE_BYTES_EXISTING if _has_existing_userdata() else _MIN_FREE_BYTES_FRESH
    assert need in (_MIN_FREE_BYTES_EXISTING, _MIN_FREE_BYTES_FRESH)
    st = emulator_status()
    assert "phase" in st and "adb_ready" in st and "boot_completed" in st
    assert st["avd"] == AVD_NAME
    assert "keyboard_hint" in st
    try:
        input_text("한글")
        raise AssertionError("non-ascii input_text should fail")
    except AdbError as exc:
        assert "non-ASCII" in str(exc) or "IME" in str(exc)
    if not adb_exe().is_file():
        print("android_emulator ok (adb missing — skip device checks)")
        raise SystemExit(0)
    print("status:", st)
    print("userdata_existing:", _has_existing_userdata(), "disk_need_gb:", need / (1024**3))
    if st["serial"]:
        print("serial ok:", st["serial"], "boot:", st["boot_completed"])
    else:
        print("android_emulator ok (no running IrisLight_Pixel serial)")
