"""iris_agent_repo_dir resolve policy self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.infrastructure.agent_runtime import (
    IRIS_AGENT_CHECKOUT_NAME,
    LEGACY_AGENT_CHECKOUT_NAME,
    iris_agent_home,
    iris_agent_repo_dir,
)


def _check_empty_home_is_canonical() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-empty-") as tmp:
        home = Path(tmp)
        got = iris_agent_repo_dir(home)
        assert got == home / IRIS_AGENT_CHECKOUT_NAME
        assert got.name == "iris-agent"


def _check_legacy_only() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-legacy-") as tmp:
        home = Path(tmp)
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        legacy.mkdir()
        got = iris_agent_repo_dir(home)
        assert got == legacy
        assert got.name == "hermes-agent"


def _check_canonical_only() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-canon-") as tmp:
        home = Path(tmp)
        canon = home / IRIS_AGENT_CHECKOUT_NAME
        canon.mkdir()
        got = iris_agent_repo_dir(home)
        assert got == canon
        assert got.name == "iris-agent"


def _check_both_prefer_canonical() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-both-") as tmp:
        home = Path(tmp)
        canon = home / IRIS_AGENT_CHECKOUT_NAME
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        canon.mkdir()
        legacy.mkdir()
        got = iris_agent_repo_dir(home)
        assert got == canon
        assert got.name == "iris-agent"


def _check_live_home() -> None:
    live = iris_agent_repo_dir()
    assert live.name in (IRIS_AGENT_CHECKOUT_NAME, LEGACY_AGENT_CHECKOUT_NAME)
    # This machine: product tree already has iris-agent.
    product = iris_agent_home()
    if (product / IRIS_AGENT_CHECKOUT_NAME).is_dir():
        assert live == product / IRIS_AGENT_CHECKOUT_NAME


def _main() -> None:
    _check_empty_home_is_canonical()
    _check_legacy_only()
    _check_canonical_only()
    _check_both_prefer_canonical()
    _check_live_home()
    print("iris_agent_repo_dir ok", iris_agent_repo_dir())


if __name__ == "__main__":
    _main()
