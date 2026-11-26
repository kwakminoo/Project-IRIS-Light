"""iris_agent_repo_dir resolve policy self-check."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from iris.infrastructure.agent_runtime import (
    ENGINE_SELECTION_FILE,
    IRIS_AGENT_CHECKOUT_NAME,
    LEGACY_AGENT_CHECKOUT_NAME,
    _OWNED_SLOT_NAME,
    iris_agent_home,
    iris_agent_repo_dir,
    read_engine_selection,
)


def _check_empty_home_is_canonical() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-empty-") as tmp:
        home = Path(tmp)
        got = iris_agent_repo_dir(home)
        assert got == home / IRIS_AGENT_CHECKOUT_NAME
        assert got.name == "iris-agent"


def _check_legacy_only_recovery() -> None:
    """hermes-only stays recovery fallback when no owned tree exists."""
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


def _check_owned_slot_beats_hermes() -> None:
    """selection missing + owned slot + hermes → owned, not silent hermes."""
    with tempfile.TemporaryDirectory(prefix="iris-repo-slot-") as tmp:
        home = Path(tmp)
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        legacy.mkdir()
        slot = home / "iris-agent.slot-bbbbbbbbbbbbbbbb"
        slot.mkdir()
        (slot / "SOURCE_MANIFEST.json").write_text("{}", encoding="utf-8")
        got = iris_agent_repo_dir(home)
        assert got == slot
        assert _OWNED_SLOT_NAME.fullmatch(got.name)


def _check_newest_owned_slot() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-slots-") as tmp:
        home = Path(tmp)
        older = home / "iris-agent.slot-cccccccccccccccc"
        newer = home / "iris-agent.slot-dddddddddddddddd"
        older.mkdir()
        newer.mkdir()
        (older / "SOURCE_MANIFEST.json").write_text("{}", encoding="utf-8")
        time.sleep(0.05)
        (newer / "SOURCE_MANIFEST.json").write_text("{}", encoding="utf-8")
        got = iris_agent_repo_dir(home)
        assert got == newer


def _check_slot_without_manifest_ignored() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-nomf-") as tmp:
        home = Path(tmp)
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        legacy.mkdir()
        bare = home / "iris-agent.slot-eeeeeeeeeeeeeeee"
        bare.mkdir()
        got = iris_agent_repo_dir(home)
        assert got == legacy


def _check_selection_active_wins() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-sel-") as tmp:
        home = Path(tmp)
        slot = home / "iris-agent.slot-ffffffffffffffff"
        slot.mkdir()
        (slot / "SOURCE_MANIFEST.json").write_text("{}", encoding="utf-8")
        (home / IRIS_AGENT_CHECKOUT_NAME).mkdir()
        (home / LEGACY_AGENT_CHECKOUT_NAME).mkdir()
        (home / ENGINE_SELECTION_FILE).write_text(
            json.dumps({"active": slot.name, "previous": LEGACY_AGENT_CHECKOUT_NAME}),
            encoding="utf-8",
        )
        got = iris_agent_repo_dir(home)
        assert got == slot


def _check_live_home() -> None:
    live = iris_agent_repo_dir()
    assert live.name in (
        IRIS_AGENT_CHECKOUT_NAME,
        LEGACY_AGENT_CHECKOUT_NAME,
    ) or _OWNED_SLOT_NAME.fullmatch(live.name)
    product = iris_agent_home()
    active, _ = read_engine_selection(product)
    if active is not None:
        assert live == active
        return
    if (product / IRIS_AGENT_CHECKOUT_NAME).is_dir():
        assert live == product / IRIS_AGENT_CHECKOUT_NAME


def _main() -> None:
    _check_empty_home_is_canonical()
    _check_legacy_only_recovery()
    _check_canonical_only()
    _check_both_prefer_canonical()
    _check_owned_slot_beats_hermes()
    _check_newest_owned_slot()
    _check_slot_without_manifest_ignored()
    _check_selection_active_wins()
    _check_live_home()
    print("iris_agent_repo_dir ok", iris_agent_repo_dir())


if __name__ == "__main__":
    _main()
