"""List UI Automation edit controls under the IRIS window."""

from __future__ import annotations

import sys

try:
    import uiautomation as auto
except ImportError:
    print("uiautomation missing")
    sys.exit(2)

win = auto.WindowControl(searchDepth=1, Name="IRIS")
if not win.Exists(3):
    print("IRIS window missing")
    sys.exit(1)
print("found", win.Name, win.BoundingRectangle)
for ctrl in win.GetChildren():
    print("child", ctrl.ControlTypeName, ctrl.Name, ctrl.ClassName, ctrl.BoundingRectangle)
    for inner in ctrl.GetChildren():
        print(
            "  ",
            inner.ControlTypeName,
            inner.Name,
            inner.ClassName,
            inner.BoundingRectangle,
        )

edits = win.GetChildren()
print("--- edits ---")
for edit in auto.WalkControl(win, maxDepth=8):
    kind = getattr(edit, "ControlTypeName", "")
    if kind in {"EditControl", "DocumentControl", "ComboBoxControl"}:
        print(kind, edit.Name, edit.AutomationId, edit.ClassName, edit.BoundingRectangle)
