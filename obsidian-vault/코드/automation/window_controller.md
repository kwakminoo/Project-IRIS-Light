# window_controller

`iris/automation/window_controller.py`

창 검색·포커스·이동·크기 (Windows).

## 주요 정의

- `class WindowInfo`
- `def get_active_window_title`
- `def list_window_titles`
- `def list_visible_windows`
- `def _list_via_macos_quartz`
- `def list_macos_windows_for_pids`
- `def is_macos_window_number_alive`
- `def _alt_tab_api`
- `def _is_cloaked`
- `def _is_alt_tab_window`
- `def _list_via_win32`
- `def _list_via_pygetwindow`
- `def find_windows_by_title_substring`
- `def focus_and_place`
- `def focus_window_by_hwnd`
- `def close_window_by_hwnd`
