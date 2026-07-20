"""Android 에뮬레이터 — 프로젝트 폴더에 AVD·데이터 저장."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANDROID_EMU_DIR = PROJECT_ROOT / "android-emulator"
AVD_HOME = ANDROID_EMU_DIR / "avd"
DATA_DIR = ANDROID_EMU_DIR / "data"
AVD_NAME = "IrisLight_Pixel"
_SYSTEM_IMAGE = "system-images;android-36;google_apis_playstore_ps16k;x86_64"
_DEVICE_ID = "pixel_9a"


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


def avdmanager_exe() -> Path:
    sdk = _sdk_root()
    name = "avdmanager.bat" if sys.platform == "win32" else "avdmanager"
    return sdk / "cmdline-tools" / "latest" / "bin" / name


def avd_config_path() -> Path:
    return AVD_HOME / f"{AVD_NAME}.avd" / "config.ini"


def is_emulator_running() -> bool:
    adb = _sdk_root() / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb")
    if not adb.is_file():
        return False
    try:
        devices = subprocess.check_output(
            [str(adb), "devices"],
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return "emulator-" in devices


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
        "disk.dataPartition.size": "32G",
        "sdcard.size": "2048M",
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


if __name__ == "__main__":
    proc = launch_emulator()
    print(f"emulator pid={proc.pid} avd={AVD_NAME} datadir={DATA_DIR}")
