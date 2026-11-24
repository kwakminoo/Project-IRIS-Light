"""U03 — unified execution policy for Speak / Control / file / shell paths.

Not a sandbox. Same helpers for GUI and headless. Reuses ActionSpec.confirm_required
semantics: model-supplied confirm is discarded; only human_confirm may approve.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from iris.system.control_surface import ActionSpec

TOOL_OUTPUT_BEGIN = "BEGIN TOOL OUTPUT (untrusted input data)"
TOOL_OUTPUT_END = "END TOOL OUTPUT"

# Markers already used by attachment / browser packing.
_UNTRUSTED_MARKERS = (
    TOOL_OUTPUT_BEGIN,
    "BEGIN ATTACHMENT TEXT (untrusted input data)",
    "BEGIN PAGE TEXT (untrusted input data)",
    "(untrusted input data)",
)

# Prompt-injection style phrases inside tool/file bodies — treat as data, not orders.
_INJECTION_RE = re.compile(
    r"(?is)("
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?"
    r"|disregard\s+(all\s+)?(previous|prior)\s+instructions?"
    r"|system\s*:\s*you\s+are"
    r"|<\s*/?\s*system\s*>"
    r"|override\s+(the\s+)?system\s+prompt"
    r")"
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


def check_path_allowed(
    root: str | Path,
    path: str | Path,
    *,
    write: bool = False,
) -> PolicyDecision:
    """Allow only paths that stay under root after normalize + resolve.

    ``write`` is reserved for future asymmetric rules; containment is the same today.
    Rejects ``..`` escape. On Windows uses resolve + normcase prefix check.
    """
    _ = write  # same containment for read/write; not a sandbox
    root_raw = str(root or "").strip()
    if not root_raw:
        return PolicyDecision(False, "root required")
    raw = str(path or "").strip()
    if not raw:
        return PolicyDecision(False, "path required")

    try:
        root_p = Path(root_raw).expanduser().resolve()
    except OSError as exc:
        return PolicyDecision(False, f"root resolve failed: {exc}")

    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            target = candidate.expanduser().resolve()
        except OSError as exc:
            return PolicyDecision(False, f"path resolve failed: {exc}")
    else:
        rel = raw.replace("\\", "/").lstrip("/")
        if not rel or ".." in rel.split("/"):
            return PolicyDecision(False, "path escapes root")
        if ".." in Path(rel).parts:
            return PolicyDecision(False, "path escapes root")
        try:
            target = (root_p / rel).resolve()
        except OSError as exc:
            return PolicyDecision(False, f"path resolve failed: {exc}")

    root_key = os.path.normcase(str(root_p))
    target_key = os.path.normcase(str(target))
    if target_key != root_key and not target_key.startswith(root_key + os.sep):
        return PolicyDecision(False, "path escapes root")
    return PolicyDecision(True)


def check_action_approval(
    spec: ActionSpec,
    args: dict[str, Any],
    human_confirm: Callable[[ActionSpec, dict[str, Any]], bool] | None,
) -> PolicyDecision:
    """Mirror Control Surface confirm gate. Model ``confirm`` alone never approves."""
    if not spec.confirm_required:
        return PolicyDecision(True)
    args.pop("confirm", None)
    if human_confirm is None:
        return PolicyDecision(False, "human confirm required")
    if not bool(human_confirm(spec, args)):
        return PolicyDecision(False, "cancelled")
    return PolicyDecision(True)


def is_untrusted_tool_payload(text: str) -> bool:
    """True when text is already marked untrusted or looks like prompt injection."""
    body = str(text or "")
    if not body:
        return False
    if any(m in body for m in _UNTRUSTED_MARKERS):
        return True
    return _INJECTION_RE.search(body) is not None


def format_tool_payload_for_model(text: str) -> str:
    """Pack tool/file body for the model as data, never as instructions.

    Hook point for Speak/Control result → prompt packing. Attachments use
    ``format_attachment_payload_for_model`` (cite markers); call this for
    generic tool output strings.
    """
    body = str(text or "")
    if TOOL_OUTPUT_BEGIN in body:
        return body
    return f"{TOOL_OUTPUT_BEGIN}:\n{body}\n{TOOL_OUTPUT_END}"


def format_attachment_payload_for_model(source: str, body: str) -> str:
    """Attachment cite packer — same untrusted-data contract as tool output."""
    src = str(source or "")
    text = str(body or "")
    return (
        f"BEGIN ATTACHMENT TEXT (untrusted input data): {src}\n"
        f"{text}\n"
        f"END ATTACHMENT TEXT: {src}"
    )
