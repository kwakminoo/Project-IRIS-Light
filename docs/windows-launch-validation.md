# Windows IRIS launch validation — 2026-10-06

## Root cause

`ChatPanel.set_model_status()` read an uninitialized local `selected`. The
startup `_begin_boot_sequence()` → `_refresh_models(probe_cloud=True)` callback
called this method, raising `UnboundLocalError`. PyQt's unhandled slot exception
terminated the process in Qt6Core.dll with Windows status `0xC0000409`.
`pythonw.exe` produced an empty launcher log, hiding the Python cause.

The existing venv points to Python 3.12.10, imports Qt 6.11 successfully, and
passes `pip check`. Both `iris/__main__.py` and `dist/IRIS.exe` exist. Setup and
launch use the same repository `.venv`; installation was not missing.

## Changes

- Remove the invalid assignment in the model status callback; preserve its
  existing runtime ID and unblock combo signals normally.
- Prefer the repository Python and current `IRIS_launcher.py` in `run.bat`.
  Quote absolute paths and forward arguments.
- Capture `%~dp0` before changing directories in both batch files. Calling a
  batch by a relative subdirectory path otherwise resolved `%~dp0` again against
  the new current directory, duplicating the directory in `setup.ps1`'s path.
- Send pip output to `Out-Host`, so the setup function returns only an integer
  exit status, eliminating spurious installation retries and warnings.
- Log interpreter/project paths, Windows exit status, and Python slot exceptions.
  Unhandled slot exceptions request an orderly application exit with status 1.

## Verification

- Actual `setup.bat` completed successfully.
- Actual `run.bat` opened a responsive window titled `IRIS`; `CloseMainWindow`
  invoked normal shutdown, then another launch and normal shutdown succeeded.
- Repeated with batch/setup/launcher files under `한글 경로 실행 검증`.
  This fixture shares the existing venv and source using directory junctions;
  it verifies Unicode/space launch and setup paths, not a fresh Python install.
- Final launch checks use `C:\Windows` as working directory and a PATH containing
  only `C:\Windows\System32`, proving launch does not require Python on PATH.
- 11 regression tests passed (`test_startup_model_status`,
  `test_launcher_failure_report`, `test_source_launch`); `pip check` passed.

`%LOCALAPPDATA%\iris-light\launcher.log` is the launch diagnostic directory.
Persistent application settings/database intentionally live under
`%USERPROFILE%\.iris-light`, where existing database and configuration files
were verified. `.env` already exists and setup preserves it.

No interpreter-path or entrypoint rename was responsible for this failure.
The failing model-status assignment was present among pre-existing working-tree
changes; unrelated chat/UI edits were preserved.
