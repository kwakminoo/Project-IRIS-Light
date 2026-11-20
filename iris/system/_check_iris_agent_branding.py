"""Product-facing Iris Agent branding — bare Hermes in setup/settings UI strings.

Fails when:
  - setup brand_label still says Hermes (must be Iris Agent)
  - setup monogram for brand key hermes is still H (must be I)
  - settings/setup user-facing quoted strings contain bare "Hermes"
  - SyncReport.summary_line still uses Iris↔Hermes

Allows: hermes-agent path comments, hermes_* identifiers, HERMES_* env,
legacy hermes_* step-id tokens in allow scrub, hermes_iris_control_sync.json.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_branding
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from iris.assets.setup_logos import brand_label
from iris.system.iris_agent_control_sync import SyncReport, project_root

_REPO = project_root()

# User-visible surfaces that must not expose bare Hermes branding.
_SURFACE_FILES = (
    _REPO / "iris" / "system" / "setup_protocol.py",
    _REPO / "iris" / "ui" / "settings" / "settings_dialog.py",
    _REPO / "iris" / "ui" / "settings" / "update_notify_box.py",
    _REPO / "iris" / "assets" / "setup_logos.py",
)

# Path / package tokens that are not product branding (stripped before Hermes check).
_ALLOW_SUBSTR = (
    "hermes-agent",
    "hermes_home",
    "hermes_install",
    "hermes_env",
    "hermes_provider",
    "agent_install",
    "agent_env",
    "agent_provider",
    "agent_runtime",
    "hermes_iris_control_sync",
    "HERMES_",
    "is_agent_",
    "probe_agent",
    "ensure_agent",
    "_agent_",
    "hermes_base_url",
    "agent_running",
    "_agent_done",
    "_step_agent_runtime",
    "_step_agent_install",
    "_step_agent_env",
    "_step_agent_provider",
    "NousResearch/hermes",
    "hermes_workers",
    "pack_hermes_result",
    "load_agent_",
    "resolve_agent_",
    "weak_agent",
)


def _string_allowed(s: str) -> bool:
    """True if every Hermes occurrence is an allowed path/id token, not branding."""
    if "Hermes" not in s and "헤르메스" not in s:
        return True
    if "헤르메스" in s:
        return False
    scrubbed = s
    for token in _ALLOW_SUBSTR:
        scrubbed = scrubbed.replace(token, "")
    return "Hermes" not in scrubbed


def _assert_setup_logos() -> None:
    assert brand_label("hermes") == "Iris Agent", brand_label("hermes")
    src = (_REPO / "iris" / "assets" / "setup_logos.py").read_text(encoding="utf-8")
    assert '"hermes": "I"' in src or "'hermes': 'I'" in src, (
        "setup_logos monogram for hermes must be I (Iris Agent), not H"
    )
    assert re.search(r'["\']hermes["\']\s*:\s*["\']H["\']', src) is None


def _assert_summary_line() -> None:
    fail_line = SyncReport(ok=False, mcp_installed=False, errors=["boom"]).summary_line()
    ok_line = SyncReport(ok=True, mcp_installed=True).summary_line()
    assert "Iris↔Hermes" not in fail_line and "Iris↔Hermes" not in ok_line
    assert fail_line.startswith("Iris↔Agent"), fail_line


def _assert_unit3_product_labels() -> None:
    """Unit 3 — setup/update/tool_choice copy is Iris Agent / sidecar, not Hermes chat path."""
    from iris.config.settings import Settings
    from iris.system.setup_protocol import CORE_STEP_LABELS

    assert Settings().agent_command == "iris-agent"
    for sid, label in CORE_STEP_LABELS.items():
        if sid.startswith("agent_") or sid == "iris_control_sync":
            assert "Hermes" not in label and "헤르메스" not in label, (sid, label)
            assert "Iris Agent" in label or "SpeakTools" in label or "MCP" in label, (
                sid,
                label,
            )

    tool_choice = (
        _REPO / "iris" / "system" / "iris_agent_tool_choice.py"
    ).read_text(encoding="utf-8")
    assert "hermes agent.tool_choice" not in tool_choice
    assert 'f"Iris Agent tool_choice:' in tool_choice or (
        "Iris Agent tool_choice:" in tool_choice
    )

    update_src = (_REPO / "iris" / "system" / "iris_agent_update.py").read_text(
        encoding="utf-8"
    )
    assert "gateway 중지" not in update_src
    # Progress lines reach the UI; do not mention :8642 as the product path.
    for line in update_src.splitlines():
        if "_note(on_progress" in line or 'on_progress("' in line:
            assert "8642" not in line, line

    hub = (_REPO / "iris" / "ui" / "ai_hub" / "ai_hub_dialog.py").read_text(
        encoding="utf-8"
    )
    assert 'startswith("Iris Agent tool_choice")' in hub
    assert "hermes agent.tool_choice" not in hub


def _collect_str(node: ast.AST | None, out: list[str]) -> None:
    if node is None:
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        out.append(node.value)
        return
    if isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append(v.value)
        return
    for child in ast.iter_child_nodes(node):
        _collect_str(child, out)


def _user_facing_strings(path: Path) -> list[str]:
    """Quoted strings that can reach UI (assignments, call args, docstrings).

    Skip # comments (not in AST). Docstrings included — setup copy often lives there.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            _collect_str(node.value, out)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            _collect_str(node.value, out)
        elif isinstance(node, ast.Call):
            for arg in node.args:
                _collect_str(arg, out)
            for kw in node.keywords:
                _collect_str(kw.value, out)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                out.append(body[0].value.value)
    return out


def _assert_surface_strings() -> None:
    hits: list[str] = []
    for path in _SURFACE_FILES:
        if not path.is_file():
            continue
        for s in _user_facing_strings(path):
            if not _string_allowed(s):
                hits.append(f"{path.relative_to(_REPO)}: {s[:120]!r}")
    assert not hits, "product-facing Hermes branding:\n  " + "\n  ".join(hits)


def _main() -> None:
    _assert_setup_logos()
    _assert_summary_line()
    _assert_surface_strings()
    _assert_unit3_product_labels()
    print("iris_agent_branding ok")
    print(f"  brand_label(hermes)={brand_label('hermes')!r}")
    print(f"  summary={SyncReport(ok=True, mcp_installed=True).summary_line()!r}")
    print("  unit3 product labels ok")


if __name__ == "__main__":
    _main()
