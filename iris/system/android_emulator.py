"""Android 에뮬레이터 — 프로젝트 폴더에 AVD·데이터 저장."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
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
# ponytail: 신규 AVD는 userdata 32G 생성이라 여유가 필요. 기존 이미지가 있으면 완화.
_MIN_FREE_BYTES_FRESH = 40 * 1024 * 1024 * 1024
_MIN_FREE_BYTES_EXISTING = 2 * 1024 * 1024 * 1024
_KEYBOARD_HINT_KO = (
    "한글은 에뮬 화면 키보드(IME) 사용. PC 키보드는 영문·특수키(hw.keyboard)용."
)

_launch_lock = threading.Lock()
_launch_in_progress = False
_launch_log_handle: object | None = None


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
    # adb emu avd name → "IrisLight_Pixel\nOK"
    for line in out.splitlines():
        name = line.strip()
        if name and name.upper() != "OK":
            return name
    return ""


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
    return bool(
        _launch_in_progress
        or _matching_emulator_serials()
        or _list_emulator_processes()
    )


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
    # hw.keyboard=yes: PC 키보드. GPU host: Windows 성능·config/qemu 정합.
    patches = {
        "disk.dataPartition.size": _DATA_PARTITION_SIZE,
        "sdcard.size": _SDCARD_SIZE,
        "hw.ramSize": "4096",
        "hw.keyboard": "yes",
        "hw.gpu.enabled": "yes",
        "hw.gpu.mode": "host",
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
            "hw.gpu.mode": "hw.gpu.mode = host",
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
    global _launch_in_progress, _launch_log_handle

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
            "host",
            # ponytail: config.ini 패치 후 깨진 quickboot 스냅샷이 adb offline을 유발할 수 있음
            "-no-snapshot-load",
        ]
        if headless:
            cmd.append("-no-window")
        _launch_log_handle.write(f"cmd: {' '.join(cmd)}\n")  # type: ignore[union-attr]
        _launch_log_handle.flush()  # type: ignore[union-attr]
        proc = subprocess.Popen(
            cmd,
            env=_emulator_env(),
            stdout=_launch_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
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
            timeout=timeout,
            env=_emulator_env(),
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
    if _list_emulator_processes() or _launch_in_progress:
        raise AdbError(
            f"AVD {AVD_NAME} 프로세스는 있으나 adb device 대기 중 — 부팅 후 다시 시도"
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


def kill_emulator() -> bool:
    """프로젝트 AVD 인스턴스 종료. 무언가 죽였으면 True."""
    global _launch_in_progress
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
            )
            killed = True
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
            killed = True
        except (subprocess.SubprocessError, OSError):
            pass
    with _launch_lock:
        _launch_in_progress = False
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
    sdk_s = str(_sdk_root())
    assert "Android" in sdk_s and "Sdk" in sdk_s
    cfg = avd_config_path()
    if cfg.is_file():
        _patch_avd_storage(cfg)
        text = cfg.read_text(encoding="utf-8")
        assert "hw.keyboard=yes" in text
        assert "hw.gpu.enabled=yes" in text
        assert "hw.gpu.mode=host" in text
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
