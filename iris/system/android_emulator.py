"""Android 에뮬레이터 — 프로젝트 폴더에 AVD·데이터 저장."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANDROID_EMU_DIR = PROJECT_ROOT / "android-emulator"
AVD_HOME = ANDROID_EMU_DIR / "avd"
DATA_DIR = ANDROID_EMU_DIR / "data"
AVD_NAME = "IrisLight_Pixel"
_SYSTEM_IMAGE = "system-images;android-36;google_apis_playstore_ps16k;x86_64"
_DEVICE_ID = "pixel_9a"
_DATA_PARTITION_SIZE = "32G"
_SDCARD_SIZE = "2048M"
# ponytail: emulator가 userdata 파티션 생성 실패로 바로 종료할 수 있어
# launch 전에 최소 디스크 여유를 가드합니다.
_MIN_FREE_BYTES = 40 * 1024 * 1024 * 1024


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
    return Path(r"C:\Users\kwakm\AppData\Local\Android\Sdk")


def emulator_exe() -> Path:
    return _sdk_root() / "emulator" / ("emulator.exe" if sys.platform == "win32" else "emulator")


def adb_exe() -> Path:
    return _sdk_root() / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb")


def avdmanager_exe() -> Path:
    sdk = _sdk_root()
    name = "avdmanager.bat" if sys.platform == "win32" else "avdmanager"
    return sdk / "cmdline-tools" / "latest" / "bin" / name


def avd_config_path() -> Path:
    return AVD_HOME / f"{AVD_NAME}.avd" / "config.ini"


def _running_emulator_serials() -> list[str]:
    adb = adb_exe()
    if not adb.is_file():
        return []
    try:
        devices = subprocess.check_output(
            [str(adb), "devices"],
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return []
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
    try:
        out = subprocess.check_output(
            [str(adb), "-s", serial, "emu", "avd", "name"],
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return out.strip()


def _matching_emulator_serials() -> list[str]:
    return [serial for serial in _running_emulator_serials() if _serial_avd_name(serial) == AVD_NAME]


def _list_emulator_processes() -> list[tuple[str, int, str]]:
    if sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -match 'emulator|qemu-system-x86_64' } | "
                "ForEach-Object { "
                "\"$($_.Name)`t$($_.ProcessId)`t$($_.CommandLine)\" "
                "}"
            ),
        ]
    else:
        cmd = ["ps", "-ax", "-o", "pid=,command="]
    try:
        output = subprocess.check_output(cmd, text=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        return []

    rows: list[tuple[str, int, str]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if sys.platform == "win32":
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            name, pid_s, cmdline = parts
        else:
            pid_s, _, cmdline = line.partition(" ")
            name = Path(cmdline.split(" ", 1)[0]).name
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if f"-avd {AVD_NAME}" not in cmdline:
            continue
        rows.append((name, pid, cmdline))
    return rows


def is_emulator_headless() -> bool:
    for name, _pid, cmdline in _list_emulator_processes():
        lowered = f"{name} {cmdline}".lower()
        if "-no-window" in lowered or "headless" in lowered:
            return True
    return False


def is_emulator_running() -> bool:
    return bool(_matching_emulator_serials() or _list_emulator_processes())


def is_emulator_available() -> tuple[bool, str]:
    """기동 가능 여부 — 현재 켜짐/꺼짐이 아니라 실행 바이너리·AVD 준비 상태.

    Returns (ok, detail). detail은 UI 한 줄용.
    """
    exe = emulator_exe()
    if not exe.is_file():
        return False, f"emulator 없음 ({exe})"
    try:
        _ensure_emulator_disk_space()
    except OSError as exc:
        return False, str(exc)
    if avd_config_path().is_file():
        return True, f"실행 가능 (AVD {AVD_NAME})"
    # AVD 없으면 launch 시 ensure_avd()로 생성 — avdmanager만 있으면 가능
    mgr = avdmanager_exe()
    if mgr.is_file():
        return True, "실행 가능 (AVD 자동 생성 가능)"
    return False, f"AVD·avdmanager 없음 ({mgr})"


def _emulator_env() -> dict[str, str]:
    env = os.environ.copy()
    env["ANDROID_AVD_HOME"] = str(AVD_HOME)
    env["ANDROID_SDK_ROOT"] = str(_sdk_root())
    env["ANDROID_HOME"] = str(_sdk_root())
    return env


def _patch_avd_storage(cfg: Path) -> None:
    if not cfg.is_file():
        return
    lines = cfg.read_text(encoding="utf-8").splitlines()
    patches = {
        "disk.dataPartition.size": _DATA_PARTITION_SIZE,
        "sdcard.size": _SDCARD_SIZE,
        "hw.ramSize": "4096",
    }
    seen = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in patches:
            out.append(f"{key}={patches[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in patches.items():
        if key not in seen:
            out.append(f"{key}={val}")
    cfg.write_text("\n".join(out) + "\n", encoding="utf-8")


def _ensure_emulator_disk_space() -> None:
    """Fail early with a readable message instead of spawning then exiting."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(DATA_DIR).free
    if free < _MIN_FREE_BYTES:
        need_gb = _MIN_FREE_BYTES / (1024**3)
        have_gb = free / (1024**3)
        raise OSError(
            f"에뮬레이터 디스크 공간 부족: 필요 약 {need_gb:.1f}GB, 현재 {have_gb:.1f}GB"
        )


def ensure_avd() -> str:
    """프로젝트 AVD가 없으면 생성하고 저장 용량을 늘린다."""
    AVD_HOME.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = avd_config_path()
    if cfg.is_file():
        _patch_avd_storage(cfg)
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
    )
    _patch_avd_storage(cfg)
    return AVD_NAME


def launch_emulator(*, headless: bool = False) -> subprocess.Popen[bytes]:
    """에뮬레이터를 프로젝트 android-emulator/data 에 userdata로 실행."""
    if not emulator_exe().is_file():
        raise FileNotFoundError(f"emulator 없음: {emulator_exe()}")
    # ponytail: no global lock — double-click can spawn two instances
    name = ensure_avd()
    _ensure_emulator_disk_space()
    cmd = [
        str(emulator_exe()),
        "-avd",
        name,
        "-datadir",
        str(DATA_DIR),
    ]
    if headless:
        cmd.append("-no-window")
    return subprocess.Popen(
        cmd,
        env=_emulator_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def restart_emulator_windowed() -> subprocess.Popen[bytes]:
    """headless/stale 프로젝트 AVD를 정리하고 창 있는 인스턴스로 다시 띄운다."""
    adb = adb_exe()
    for serial in _matching_emulator_serials():
        try:
            subprocess.run(
                [str(adb), "-s", serial, "emu", "kill"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            pass

    for _name, pid, _cmdline in _list_emulator_processes():
        if sys.platform == "win32":
            kill_cmd = ["taskkill", "/PID", str(pid), "/F", "/T"]
        else:
            kill_cmd = ["kill", "-TERM", str(pid)]
        try:
            subprocess.run(
                kill_cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (subprocess.SubprocessError, OSError):
            pass

    deadline = time.time() + 15
    while time.time() < deadline:
        if not is_emulator_running():
            break
        time.sleep(0.5)
    return launch_emulator(headless=False)


if __name__ == "__main__":
    proc = launch_emulator()
    print(f"emulator pid={proc.pid} avd={AVD_NAME} datadir={DATA_DIR}")
