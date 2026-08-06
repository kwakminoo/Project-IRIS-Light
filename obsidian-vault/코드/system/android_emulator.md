# android_emulator

`iris/system/android_emulator.py`

Android 에뮬레이터 — 프로젝트 폴더에 AVD·데이터 저장.

## 주요 정의

- `def _sdk_root`
- `def emulator_exe`
- `def adb_exe`
- `def avdmanager_exe`
- `def avd_config_path`
- `def launch_log_path`
- `def _has_existing_userdata`
- `def _running_emulator_serials`
- `def _serial_avd_name`
- `def _matching_emulator_serials`
- `def _list_emulator_processes`
- `def is_emulator_headless`
- `def is_emulator_running`
- `def is_emulator_available`
- `def _emulator_env`
- `def _patch_avd_storage`
- `def _ensure_emulator_disk_space`
- `def ensure_avd`
- `def _clear_launch_flag_later`
- `def launch_emulator`
- `def restart_emulator_windowed`
- `class AdbError`
- `def adb_run`
- `def require_serial`
- `def _getprop`
- `def is_boot_completed`
- `def wait_for_boot`
- `def read_launch_log_tail`
- `def emulator_status`
- `def kill_emulator`
- `def _escape_adb_input_text`
- `def install_apk`
- `def start_app`
- `def press_key`
- `def input_text`
- `def tap`
- `def swipe`
- `def screenshot`
- `def logcat_tail`
