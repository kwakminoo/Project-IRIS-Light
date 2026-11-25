"""Stale ref recovery: snapshot → match intent → one retry or re-approval.

Never auto-repeats a sensitive act when the target identity changed or the
match is ambiguous. Wire/tool source is irrelevant here (Actor comes from parse).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from iris.browser.types import BrowserSnapshot, PageNode

MatchStatus = Literal["exact", "ambiguous", "missing"]
PlanAction = Literal["retry", "needs_reapproval"]


@dataclass(frozen=True)
class StaleRefMatch:
    status: MatchStatus
    node: PageNode | None = None


@dataclass(frozen=True)
class StaleRefPlan:
    action: PlanAction
    new_ref: str = ""
    detail: str = ""


def target_identity(node: PageNode) -> tuple[str, str, str, str]:
    return (node.role or "", node.name or "", node.frame or "", node.context or "")


def match_node_intent(intent: PageNode, snap: BrowserSnapshot) -> StaleRefMatch:
    """Match approved intent by role/name/frame. Unique hit → exact; else low confidence."""
    role = intent.role or ""
    name = intent.name or ""
    frame = intent.frame or ""
    if not role and not name:
        return StaleRefMatch("missing")

    framed = [
        n
        for n in snap.nodes
        if (n.role or "") == role and (n.name or "") == name and (n.frame or "") == frame
    ]
    if len(framed) == 1:
        return StaleRefMatch("exact", framed[0])
    if len(framed) > 1:
        return StaleRefMatch("ambiguous")

    if frame:
        # Intent had a frame; no framed hit → do not guess across frames.
        return StaleRefMatch("missing")

    bare = [n for n in snap.nodes if (n.role or "") == role and (n.name or "") == name]
    if len(bare) == 1:
        return StaleRefMatch("exact", bare[0])
    if len(bare) > 1:
        return StaleRefMatch("ambiguous")
    return StaleRefMatch("missing")


def plan_stale_ref_recovery(
    *,
    intent: PageNode | None,
    fresh: BrowserSnapshot,
    approved_sensitive: bool,
    new_is_sensitive: Callable[[PageNode], bool],
) -> StaleRefPlan:
    """Decide one retry vs structured re-approval. Caller executes at most once."""
    if intent is None:
        return StaleRefPlan("needs_reapproval", detail="needs_reapproval")
    matched = match_node_intent(intent, fresh)
    if matched.status != "exact" or matched.node is None:
        return StaleRefPlan("needs_reapproval", detail="needs_reapproval")
    node = matched.node
    same = target_identity(intent) == target_identity(node)
    sensitive_now = bool(new_is_sensitive(node))
    if sensitive_now and not (approved_sensitive and same):
        return StaleRefPlan("needs_reapproval", detail="needs_reapproval")
    if approved_sensitive and not same:
        return StaleRefPlan("needs_reapproval", detail="needs_reapproval")
    return StaleRefPlan("retry", new_ref=node.ref, detail="")
