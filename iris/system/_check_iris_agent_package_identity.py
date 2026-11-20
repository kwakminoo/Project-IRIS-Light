"""F1 — install overlay renames live pyproject package identity to iris-agent.

Console scripts iris-agent / iris target iris_agent_cli.main (F3).
Probe names are iris_agent_cli / iris_cli only.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_package_identity
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from textwrap import dedent

from iris.infrastructure import agent_runtime as runtime
from iris.system.iris_agent_package_identity import (
    apply_iris_agent_package_identity_overlay,
)


_MINIMAL_PYPROJECT = dedent(
    """\
    [project]
    name = "hermes-agent"
    version = "0.0.0"
    dependencies = []

    [project.optional-dependencies]
    all = [
      "hermes-agent[cron]",
      "hermes-agent[mcp]",
    ]

    [project.scripts]
    hermes = "hermes_cli.main:main"
    hermes-agent = "agent.legacy_cli:main"

    [tool.setuptools.packages.find]
    where = ["."]
    include = [
      "hermes_cli",
      "hermes_cli.*",
    ]
    """
)

_PACKAGES_FIND_IRIS_ENTRIES = (
    '"iris_agent_cli"',
    '"iris_agent_cli.*"',
    '"iris_cli"',
    '"iris_cli.*"',
)


def _check_overlay_rewrites_temp_pyproject() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pyproject = root / "pyproject.toml"
        pyproject.write_text(_MINIMAL_PYPROJECT, encoding="utf-8")
        msgs = apply_iris_agent_package_identity_overlay(root)
        assert msgs, "overlay should return at least one status message"
        text = pyproject.read_text(encoding="utf-8")
        assert 'name = "iris-agent"' in text
        assert 'name = "hermes-agent"' not in text
        assert '"iris-agent[cron]"' in text
        assert '"hermes-agent[' not in text
        assert 'hermes = "hermes_cli.main:main"' in text
        assert 'iris-agent = "iris_agent_cli.main:main"' in text
        assert 'iris = "iris_agent_cli.main:main"' in text


def _check_packages_find_includes_iris_cli() -> None:
    """Editable finder must list iris_agent_cli / iris_cli for probe."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pyproject = root / "pyproject.toml"
        pyproject.write_text(_MINIMAL_PYPROJECT, encoding="utf-8")
        apply_iris_agent_package_identity_overlay(root)
        text = pyproject.read_text(encoding="utf-8")
        for entry in _PACKAGES_FIND_IRIS_ENTRIES:
            assert entry in text, f"packages.find missing {entry}"
        # Idempotent: second apply must not duplicate.
        apply_iris_agent_package_identity_overlay(root)
        text2 = pyproject.read_text(encoding="utf-8")
        for entry in _PACKAGES_FIND_IRIS_ENTRIES:
            assert text2.count(entry) == 1, f"duplicate packages.find entry {entry}"


def _check_probe_iris_cli_only() -> None:
    # HEAD may still probe hermes_cli; packages.find overlay is the landable fix.
    if not hasattr(runtime, "AGENT_CLI_PROBE_NAMES"):
        return
    names = runtime.AGENT_CLI_PROBE_NAMES
    assert "hermes_cli" not in names
    assert "iris_agent_cli" in names or "iris_cli" in names


def _check_baseline_wires_package_identity() -> None:
    src = inspect.getsource(runtime.apply_iris_agent_baseline_overlays)
    assert "apply_iris_agent_package_identity_overlay" in src


def _check_soft_fail_missing_pyproject() -> None:
    with tempfile.TemporaryDirectory() as td:
        msgs = apply_iris_agent_package_identity_overlay(Path(td))
        assert msgs
        assert any("missing" in m.lower() or "pyproject" in m.lower() for m in msgs)


def main() -> None:
    _check_overlay_rewrites_temp_pyproject()
    _check_packages_find_includes_iris_cli()
    _check_probe_iris_cli_only()
    _check_baseline_wires_package_identity()
    _check_soft_fail_missing_pyproject()
    print("iris_agent_package_identity ok")


if __name__ == "__main__":
    main()
