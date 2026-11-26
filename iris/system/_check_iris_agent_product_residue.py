"""Fail if Iris product code still exposes Hermes-named APIs / step ids.

Allowed leftovers (not scanned as failures when only these appear):
- HERMES_HOME env assignments
- Upstream URL strings (github.com/NousResearch/hermes-agent, …)
- Legacy path fallbacks that look for hermes.exe as last resort
- Comments that say \"legacy hermes\"
- Test fixtures with file:///tmp/hermes-agent style paths

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_product_residue
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = (_ROOT / "iris", _ROOT / "tests")

# Product symbols that must not remain as identifiers / CORE step literals.
_FORBIDDEN_IDENT = (
    "hermes_executable",
    "resolve_hermes_api_key",
    "hermes_install_lock",
    "load_hermes_dotenv",
    "is_weak_hermes_api_key",
    "infer_hermes_provider",
    "ensure_hermes_provider_config",
    "hermes_home_agent_root",
    "_hermes_prefer_bypass",
    "_hermes_official_failed",
)
_FORBIDDEN_PREFIX = (
    "install_hermes_",
    "probe_hermes_",
    "apply_hermes_",
    "_step_hermes_",
    "_install_hermes_",
    "force_retire_hermes_",
    "ensure_hermes_stdio_",
)
_FORBIDDEN_DEF = re.compile(r"(?m)^\s*def\s+hermes_home\b")
# Fresh product defs must use iris_agent_* (allow hermes_cli mentions in comments/strings).
_FORBIDDEN_DEF_PREFIX = re.compile(
    r"(?m)^\s*def\s+(?:hermes_|list_hermes_|read_hermes_|verify_hermes_|"
    r"ensure_hermes_|force_retire_hermes|install_hermes_)\w*"
)
# Dual-param kwarg shims removed — signatures must use agent_* only.
_FORBIDDEN_PARAM = re.compile(
    r"(?m)^\s*(?:hermes_command|hermes_base_url)\s*:"
)
_FORBIDDEN_STEP_IN_CORE = re.compile(
    r'"(hermes_install|hermes_env|hermes_provider)"'
)
_AGENT_CMD_DEFAULT = re.compile(
    r'agent_command\s*(?::\s*str\s*)?=\s*"hermes"'
    r'|IRIS_AGENT_COMMAND"\s*,\s*"hermes"'
    r'|get\(\s*"IRIS_AGENT_COMMAND"\s*,\s*"hermes"\s*\)'
)

# Lines that may mention hermes.exe / legacy without failing the pin.
_ALLOW_LINE = re.compile(
    r"HERMES_HOME|HERMES_REPO|"
    r"hermes-agent\.nousresearch|NousResearch/hermes-agent|"
    r"legacy hermes|hermes\.exe|hermes-agent\.exe|"
    r"hermes_cli|file:///tmp/hermes-agent|"
    r"iris-hermes-update://"
    r"|_LEGACY_SETUP_STEPS|"
    r"hermes_install.:|hermes_env.:|hermes_provider.:"  # migration map keys
)


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for base in _SCAN_ROOTS:
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if any(part in {".worktrees", "vendor", "graphify-out"} for part in p.parts):
                continue
            # _check_* modules intentionally list old names as forbid lists.
            if p.name.startswith("_check_"):
                continue
            out.append(p)
    return out


def _line_allowed(line: str) -> bool:
    return bool(_ALLOW_LINE.search(line))


def _scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = str(path.relative_to(_ROOT)).replace("\\", "/")
    hits: list[str] = []

    if _FORBIDDEN_DEF.search(text):
        hits.append(f"{rel}: def hermes_home")
    for m in _FORBIDDEN_DEF_PREFIX.finditer(text):
        snippet = m.group(0).strip()
        # Upstream module hermes_cli may appear in comments next to a def; still
        # forbid the def name itself when it matches the product prefixes above.
        hits.append(f"{rel}: {snippet}")
    for m in _FORBIDDEN_PARAM.finditer(text):
        hits.append(f"{rel}: forbidden param {m.group(0).strip()}")

    # CORE registries: only flag step id literals outside migration maps / allow lines.
    is_setup = path.name == "setup_protocol.py"
    for i, line in enumerate(text.splitlines(), 1):
        if _line_allowed(line):
            continue
        for name in _FORBIDDEN_IDENT:
            if name in line:
                hits.append(f"{rel}:{i}: {name}")
        for pref in _FORBIDDEN_PREFIX:
            if pref in line:
                hits.append(f"{rel}:{i}: {pref}*")
        if _AGENT_CMD_DEFAULT.search(line):
            hits.append(f"{rel}:{i}: agent_command default hermes")
        # Step ids in CORE_STEP_* / VISIBLE / wizard registries — not migration dict.
        if _FORBIDDEN_STEP_IN_CORE.search(line):
            if " _LEGACY" in line or "_LEGACY_SETUP_STEPS" in text[
                max(0, text.find(line) - 80) : text.find(line) + 1
            ]:
                continue
            # migration dict values appear as "hermes_install": "iris_agent_install"
            if re.search(
                r'"(hermes_install|hermes_env|hermes_provider)"\s*:\s*"iris_agent_',
                line,
            ):
                continue
            # Only flag if file is a registry / check that should use new ids.
            if is_setup and (
                "CORE_STEP" in text[: text.find(line) + 1][-400:]
                or "VISIBLE_CONSOLE" in line
                or "_core_runners" in text[max(0, text.find(line) - 200) : text.find(line)]
            ):
                hits.append(f"{rel}:{i}: legacy step id literal")
            elif path.name in {
                "setup_logos.py",
                "setup_wizard.py",
                "_check_setup_protocol.py",
                "_check_setup_hermes_live.py",
            } or path.name.startswith("test_setup"):
                hits.append(f"{rel}:{i}: legacy step id literal")
            elif '"hermes_install"' in line or '"hermes_env"' in line or '"hermes_provider"' in line:
                # Tests asserting old step ids
                if "test_" in path.name or path.parts[-2] == "tests":
                    hits.append(f"{rel}:{i}: legacy step id literal")

    return hits


def main() -> None:
    # Explicit CORE registry check (authoritative).
    setup = (_ROOT / "iris" / "system" / "setup_protocol.py").read_text(
        encoding="utf-8", errors="replace"
    )
    # Extract CORE_STEP_IDS / LABELS / VISIBLE_CONSOLE_STEPS blocks roughly.
    for needle in ('"hermes_install"', '"hermes_env"', '"hermes_provider"'):
        # Allowed only inside _LEGACY_SETUP_STEPS map as keys.
        for m in re.finditer(re.escape(needle), setup):
            window = setup[max(0, m.start() - 120) : m.start() + 80]
            if "_LEGACY_SETUP_STEPS" in window or "legacy setup step" in window:
                continue
            # comment-only lines ok
            line_start = setup.rfind("\n", 0, m.start()) + 1
            line = setup[line_start : setup.find("\n", m.start())]
            if line.strip().startswith("#"):
                continue
            raise AssertionError(
                f"setup_protocol still has {needle} outside legacy remap: {line.strip()}"
            )

    settings = (_ROOT / "iris" / "config" / "settings.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert 'agent_command: str = "iris-agent"' in settings
    assert 'IRIS_AGENT_COMMAND", "iris-agent"' in settings or (
        'get("IRIS_AGENT_COMMAND", "iris-agent")' in settings
    )
    assert 'agent_command: str = "hermes"' not in settings

    all_hits: list[str] = []
    for path in _iter_py_files():
        all_hits.extend(_scan_file(path))

    # Dedupe while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for h in all_hits:
        if h in seen:
            continue
        seen.add(h)
        uniq.append(h)

    assert not uniq, "Hermes product residue remains:\n  " + "\n  ".join(uniq[:40])
    print("iris_agent_product_residue ok", len(_iter_py_files()), "files")


if __name__ == "__main__":
    main()
