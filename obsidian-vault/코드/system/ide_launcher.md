# ide_launcher

`iris/system/ide_launcher.py`

IDE 경로 해석 · 실행 · 이미 실행 중 탐지 (Windows 우선).

## 주요 정의

- `class IdeSpec`
- `def _local_appdata`
- `def _program_files`
- `def _program_files_x86`
- `def _expand`
- `def ide_catalog`
- `def get_ide_spec`
- `def _first_existing`
- `def _which_filtered`
- `def resolve_ide_exe`
- `def resolve_ide_cli`
- `def is_ide_installed`
- `def find_running_ide`
- `def _target_pids_for_ide`
- `def _list_ide_windows_macos`
- `def list_ide_windows`
- `def is_cursor_agents_title`
- `def is_generic_ide_title`
- `def workspace_title_lost_context`
- `def wait_for_new_ide_window`
- `def _popen_detached`
- `def launch_ide`
- `def open_folder_in_ide`
- `def open_file_in_ide`
- `def wait_for_ide_window`
- `def open_install_url`

## 내부 의존성

- [[window_controller]]
