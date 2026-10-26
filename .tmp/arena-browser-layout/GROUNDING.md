# Grounding: IRIS dedicated browser vs IDE layout (HEAD)

Source of truth is the workspace at HEAD. `.tmp/browser-unify-how/EXPLANATION.md` is stale.

## What the user wants

Dedicated browser screen must use the same layout as IRIS IDE after a folder is open:

- Left: full webpage (like the IDE left editor)
- Right: same IRIS chat column
- Top: existing DragTab / nav icons so home and other screens remain reachable
- Address bar and nav buttons sit on the left browser region, not a new chrome
- No new window or popup
- Keep IDE splitter / screen-switch behavior

This is NOT "put a browser inside the IDE window." It is an independent screen that copies the IDE layout.

IDE-internal browser stays a separate feature: swap Theia for BrowserPanel on IrisIdeWindow._stack.

Keep YouTube mini-player (chat-anchored Qt.Tool, resize/drag, restore, persist across screens).

Reuse BrowserSession and ViewHost. Do not rewrite the command bus.

## HEAD facts (verified)

- After folder open, IRIS IDE is MainWindow + IdeUnifiedShell 80:20. Theia is a frameless child HWND synced onto ide_host, not a Qt.Widget child.
- Dedicated BrowserWorkspacePage is mail/calendar clone: _workspace_stack page, [820, 420], left sidebar still visible. It does not use IdeUnifiedShell.
- One shared BrowserPanel / QWebEngineView. place_browser_panel vs reclaim_browser_panel reparent it.
- show_browser_workspace is one surface provider. If _ui_mode == ide_companion it calls _show_browser_in_ide (covers Theia). Else it shows BrowserWorkspacePage.
- ViewHost is Literal["panel", "mini"] only. Dedicated and IDE-internal are both "panel".
- Mini is Qt.Tool overlay of the same view. ChatPanel is one widget remounted via addWidget only. setParent(None) is forbidden.
- Catalog/skill still say "Iris IDE browser stack page".
- Contracts: iris.ui.workspaces._check_browser_workspace, iris.ui.browser._check_mini_player, iris.system._check_browser_scenarios.

## Load-bearing files

- iris/ui/window/main_window.py
- iris/ui/workspaces/ide_companion_page.py (IdeUnifiedShell, IdeCompanionPage)
- iris/ui/workspaces/browser_workspace_page.py
- iris/ui/workspaces/iris_ide_window.py
- iris/ui/browser/panel.py
- iris/ui/browser/mini_player.py
- iris/browser/session.py, iris/browser/types.py
- iris/ui/control_actions/browser.py
- iris/ui/widgets/drag_tab.py
