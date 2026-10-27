"""Walk UI Automation under the IRIS window via comtypes."""

from __future__ import annotations

from comtypes import GUID
from comtypes.client import CreateObject
from comtypes.gen.UIAutomationClient import (
    CUIAutomation,
    TreeScope_Descendants,
    UIA_ControlTypePropertyId,
    UIA_NamePropertyId,
    UIA_ClassNamePropertyId,
    UIA_AutomationIdPropertyId,
    UIA_BoundingRectanglePropertyId,
)

UIA = CreateObject(CUIAutomation)
root = UIA.GetRootElement()
cond = UIA.CreatePropertyCondition(UIA_NamePropertyId, "IRIS")
wins = root.FindAll(TreeScope_Descendants, cond)
print("named IRIS", wins.Length)
target = None
for i in range(wins.Length):
    el = wins.GetElement(i)
    print("win", el.CurrentName, el.CurrentClassName, el.CurrentControlType)
    if el.CurrentClassName:
        target = el
        break
if target is None:
    cond2 = UIA.CreatePropertyCondition(UIA_ClassNamePropertyId, "Qt5152QWindowIcon")
    print("fallback class search skipped if none")
    raise SystemExit(1)
kids = target.FindAll(TreeScope_Descendants, UIA.CreateTrueCondition())
print("descendants", kids.Length)
for i in range(min(kids.Length, 80)):
    el = kids.GetElement(i)
    name = el.CurrentName or ""
    cls = el.CurrentClassName or ""
    auto_id = el.CurrentAutomationId or ""
    ctype = el.CurrentControlType
    rect = el.CurrentBoundingRectangle
    print(f"{i} type={ctype} name={name!r} class={cls!r} id={auto_id!r} rect=({rect.left},{rect.top},{rect.right},{rect.bottom})")
