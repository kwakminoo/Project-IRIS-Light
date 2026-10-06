# IDE folder-open crash — 2026-10-06

The user's `launcher.log` identifies this call chain:

`_on_iris_ide_hero_folder` → `_open_iris_ide_folder` →
`_ensure_iris_ide_window` → `IdeSnapRedirect.install` →
`iris.learning.win32_hooks` import.

Importing `LRESULT` from `ctypes.wintypes` raised `ImportError` on the installed
Python 3.12.10. The unhandled Qt slot exception caused the application to exit.

The hook module now defines `LRESULT` using `ctypes.c_ssize_t`, uses
`WINFUNCTYPE`, and declares the argument/return types of `SetWindowsHookExW`,
`CallNextHookEx`, and `UnhookWindowsHookEx`. This also prevents 64-bit hook
handles/results from being truncated to ctypes' default 32-bit integer.
The optional snap hook logs an initialization import/OS error and returns false
so it cannot prevent the IDE window from opening.

API references: [Microsoft SetWindowsHookExW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowshookexw),
[Python ctypes](https://docs.python.org/3.13/library/ctypes.html).

## Verification

- 16 regression tests passed: Windows hook import and pointer-width callback,
  actual hook install/uninstall/reinstall, optional-hook failure handling,
  Theia workspace/new-window launch arguments, model startup and source launcher.
- `scripts/check_ide_folder_open.py` creates a folder through the real hero
  `_pick_create` handler and its created/opened Qt signals. Only the parent
  directory picker is substituted; it selects a temporary path containing
  Korean text and spaces.
- The real MainWindow folder-open handler, Win32 hook, background launch worker,
  installed Theia runtime and QWebEngineView run. The Theia page loads, the same
  folder is reopened and loads again, both windows remain visible, and the
  workspace and native hook are verified before normal shutdown.
- The integration test uses `MainWindow(test_mode=True)` and an isolated SQLite
  database to avoid unrelated boot/install/voice jobs or changes to the user's
  project settings. Test paths are not written to recent folders.

Result: `PASS created folder -> IDE loaded -> reopen -> IRIS alive`.
