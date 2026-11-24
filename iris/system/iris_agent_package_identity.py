"""Install-time soft patch: live pyproject package name hermes-agent → iris-agent.

Console scripts iris-agent / iris point at iris_agent_cli.main (F3).
Legacy hermes script may keep hermes_cli.main (reverse shim after F3).
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

_NAME_RE = re.compile(
    r'(?m)^(name\s*=\s*")hermes-agent("\s*)$',
)
_SCRIPT_IRIS_AGENT = 'iris-agent = "iris_agent_cli.main:main"'
_SCRIPT_IRIS = 'iris = "iris_agent_cli.main:main"'
_SCRIPTS_HEADER = "[project.scripts]"
_PACKAGES_FIND_HEADER = "[tool.setuptools.packages.find]"
_PACKAGES_FIND_IRIS = (
    '"iris_agent_cli"',
    '"iris_agent_cli.*"',
    '"iris_cli"',
    '"iris_cli.*"',
)


def ensure_iris_agent_windows_console_shim(agent_root: Path) -> list[str]:
    """If Scripts has hermes.exe but no iris-agent.exe, copy a Windows shim.

    Overlay already adds pyproject console scripts; old trees may still only
    have hermes.exe until the next uv sync. Soft-fail; never raise.
    """
    if sys.platform != "win32":
        return []
    scripts = Path(agent_root) / "venv" / "Scripts"
    if not scripts.is_dir():
        return []
    target = scripts / "iris-agent.exe"
    if target.is_file():
        return ["console shim: iris-agent.exe present"]
    for src_name in ("hermes.exe", "hermes-agent.exe", "iris.exe"):
        src = scripts / src_name
        if not src.is_file():
            continue
        try:
            shutil.copy2(src, target)
        except OSError as exc:
            return [f"console shim: copy fail: {exc}"]
        return [f"console shim: copied {src_name} → iris-agent.exe"]
    return ["console shim: no legacy exe to copy"]


def apply_iris_agent_package_identity_overlay(agent_root: Path) -> list[str]:
    """Rewrite checkout pyproject identity to iris-agent. Soft-fail; never raise."""
    root = Path(agent_root)
    path = root / "pyproject.toml"
    if not path.is_file():
        return [f"package identity: pyproject missing at {path}"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"package identity: read fail: {exc}"]

    original = text
    text, n_name = _NAME_RE.subn(r"\1iris-agent\2", text, count=1)
    text = text.replace('"hermes-agent[', '"iris-agent[')
    text = text.replace("'hermes-agent[", "'iris-agent[")
    text = _ensure_script_entries(text)
    text = _ensure_packages_find_iris(text)

    msgs: list[str] = []
    if text == original:
        if 'name = "iris-agent"' in text and "iris-agent =" in text:
            msgs.append("package identity: already iris-agent")
        else:
            msgs.append("package identity: no hermes-agent markers — skipped")
    else:
        try:
            path.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            return [f"package identity: write fail: {exc}"]

        bits = []
        if n_name:
            bits.append("name→iris-agent")
        if '"iris-agent[' in text and '"hermes-agent[' not in text:
            bits.append("extras self-refs")
        if _SCRIPT_IRIS_AGENT in text:
            bits.append("scripts iris-agent")
        if all(e in text for e in _PACKAGES_FIND_IRIS):
            bits.append("packages.find iris")
        detail = ", ".join(bits) if bits else "patched"
        msgs.append(f"package identity: {detail}")

    msgs.extend(ensure_iris_agent_windows_console_shim(root))
    return msgs


def _ensure_script_entries(text: str) -> str:
    if _SCRIPTS_HEADER not in text:
        return text
    # Retarget F1-era iris-* scripts that still pointed at hermes_cli.main.
    text = re.sub(
        r'(?m)^(iris-agent\s*=\s*")hermes_cli\.main:main("\s*)$',
        r"\1iris_agent_cli.main:main\2",
        text,
    )
    text = re.sub(
        r'(?m)^(iris\s*=\s*")hermes_cli\.main:main("\s*)$',
        r"\1iris_agent_cli.main:main\2",
        text,
    )
    if re.search(r"(?m)^iris-agent\s*=", text):
        # Still add bare ``iris`` if cheap and missing.
        if not re.search(r"(?m)^iris\s*=", text):
            text = _insert_after_scripts_line(text, r"(?m)^iris-agent\s*=.*$", _SCRIPT_IRIS)
        return text
    # Prefer after legacy hermes console script; else right under the header.
    if re.search(r"(?m)^hermes\s*=", text):
        return _insert_after_scripts_line(
            text,
            r"(?m)^hermes\s*=.*$",
            f"{_SCRIPT_IRIS_AGENT}\n{_SCRIPT_IRIS}",
        )
    idx = text.find(_SCRIPTS_HEADER)
    end = text.find("\n", idx)
    if end < 0:
        return text + f"\n{_SCRIPT_IRIS_AGENT}\n{_SCRIPT_IRIS}\n"
    insert = f"\n{_SCRIPT_IRIS_AGENT}\n{_SCRIPT_IRIS}"
    return text[: end + 1] + insert + "\n" + text[end + 1 :].lstrip("\n")


def _insert_after_scripts_line(text: str, line_re: str, block: str) -> str:
    m = re.search(line_re, text)
    if not m:
        return text
    at = m.end()
    return text[:at] + "\n" + block + text[at:]


def _ensure_packages_find_iris(text: str) -> str:
    """Register iris_agent_cli / iris_cli in setuptools packages.find include."""
    if _PACKAGES_FIND_HEADER not in text:
        return text
    missing = [e for e in _PACKAGES_FIND_IRIS if e not in text]
    if not missing:
        return text
    block = "\n".join(f"      {e}," for e in missing)
    # Prefer immediately after hermes_cli.*; else right after include = [.
    m = re.search(r'(?m)^(\s*)"hermes_cli\.\*"\s*,?\s*$', text)
    if m:
        rebuilt = f'{m.group(1)}"hermes_cli.*",\n{block}'
        return text[: m.start()] + rebuilt + text[m.end() :]
    m_inc = re.search(r"(?m)^(\s*include\s*=\s*\[)\s*$", text)
    if m_inc:
        return text[: m_inc.end()] + "\n" + block + text[m_inc.end() :]
    return text
