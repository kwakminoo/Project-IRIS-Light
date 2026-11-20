"""PR-E — product install write dest is iris-agent (not hermes-agent primary).

Allows ``hermes-agent`` only as resolver fallback / migrate soft-fail / retire
cleanup. New empty homes must write ``iris-agent``.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_checkout_write_dest
"""

from __future__ import annotations

import ast
import re
import tempfile
from pathlib import Path

from iris.infrastructure.agent_runtime import (
    IRIS_AGENT_CHECKOUT_NAME,
    LEGACY_AGENT_CHECKOUT_NAME,
    iris_agent_checkout_dir,
    iris_agent_checkout_write_dir,
    migrate_legacy_checkout_dirname,
)

_ROOT = Path(__file__).resolve().parents[2]

# Product modules that must not hardcode live write dest as hermes-agent alone.
_WRITE_MODULES = (
    "iris/engine/_home.py",
    "iris/system/iris_agent_install.py",
)

# Bare ``home / "hermes-agent"`` (or Path(home)) as a write live target is banned
# unless the same expression builds via write_dir / IRIS_AGENT_CHECKOUT_NAME.
_LIVE_HERMES = re.compile(
    r"""(?:Path\s*\(\s*home\s*\)|home)\s*/\s*[\"']hermes-agent[\"']"""
)


def _check_behavior() -> None:
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        # Empty home → primary write is iris-agent.
        assert iris_agent_checkout_write_dir(home) == home / IRIS_AGENT_CHECKOUT_NAME
        assert iris_agent_checkout_dir(home) == home / LEGACY_AGENT_CHECKOUT_NAME

        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        legacy.mkdir()
        (legacy / "KEEP").write_text("1", encoding="utf-8")
        status, detail = migrate_legacy_checkout_dirname(home)
        assert status == "ok", detail
        assert (home / IRIS_AGENT_CHECKOUT_NAME / "KEEP").is_file()
        assert not legacy.exists()
        assert iris_agent_checkout_dir(home) == home / IRIS_AGENT_CHECKOUT_NAME
        assert iris_agent_checkout_write_dir(home) == home / IRIS_AGENT_CHECKOUT_NAME

        # Soft-fail path: only locked hermes-agent → write stays on legacy.
        home2 = home / "half"
        home2.mkdir()
        only = home2 / LEGACY_AGENT_CHECKOUT_NAME
        only.mkdir()
        assert iris_agent_checkout_write_dir(home2) == only
        assert iris_agent_checkout_dir(home2) == only


def _check_source_scrape() -> None:
    for rel in _WRITE_MODULES:
        path = _ROOT / rel
        text = path.read_text(encoding="utf-8")
        # Prefer write_dir / IRIS_AGENT_CHECKOUT_NAME for live dest.
        assert "iris_agent_checkout_write_dir" in text or "IRIS_AGENT_CHECKOUT_NAME" in text, (
            f"{rel}: must use iris_agent_checkout_write_dir or IRIS_AGENT_CHECKOUT_NAME"
        )
        # Ban primary live assignment that is only hermes-agent literal.
        # Allow LEGACY_AGENT_CHECKOUT_NAME and retire/fallback mentions.
        for match in _LIVE_HERMES.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start:line_end if line_end != -1 else len(text)]
            if "LEGACY" in line or "fallback" in line.lower() or "retire" in line.lower():
                continue
            # Comment-only lines ok.
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            raise AssertionError(
                f"{rel}: primary write dest still hardcodes hermes-agent: {line.strip()}"
            )
        # AST: install_into dest must not be Constant 'hermes-agent' alone via BinOp.
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "dest":
                    # dest = ... must involve write_dir call or iris-agent name.
                    src = ast.dump(node.value)
                    assert (
                        "iris_agent_checkout_write_dir" in src
                        or "IRIS_AGENT_CHECKOUT_NAME" in src
                        or "iris-agent" in src
                    ), f"{rel}: dest assign must target iris-agent write path"


def main() -> None:
    _check_behavior()
    _check_source_scrape()
    print("iris_agent_checkout_write_dest ok")


if __name__ == "__main__":
    main()
