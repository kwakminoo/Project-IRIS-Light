"""iris_agent_repo_dir resolve policy self-check."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from iris.infrastructure.agent_runtime import (
    ENGINE_SELECTION_FILE,
    IRIS_AGENT_CHECKOUT_NAME,
    LEGACY_AGENT_CHECKOUT_NAME,
    _OWNED_SLOT_NAME,
    iris_agent_home,
    iris_agent_repo_dir,
    read_engine_selection,
    selected_owned_engine,
)
from iris.system.iris_agent_install import vendor_iris_agent_core_root


def write_owned_slot_fixture(slot: Path) -> Path:
    """Copy the manifest inputs for selection contracts with a fake interpreter."""
    vendor = vendor_iris_agent_core_root()
    manifest = json.loads((vendor / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    for name in ("SOURCE_MANIFEST.json", *manifest["sha256"]):
        (slot / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(vendor / name, slot / name)
    python = slot / ("venv/Scripts/python.cmd" if sys.platform == "win32" else "venv/bin/python")
    python.parent.mkdir(parents=True, exist_ok=True)
    python.touch()
    return python


def _select(home: Path, active: Path, previous: Path | None = None) -> None:
    (home / ENGINE_SELECTION_FILE).write_text(
        json.dumps({"active": active.name, "previous": previous.name if previous else None}),
        encoding="utf-8",
    )


def _check_empty_home_is_canonical() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-empty-") as tmp:
        home = Path(tmp)
        got = iris_agent_repo_dir(home)
        assert got == home / IRIS_AGENT_CHECKOUT_NAME
        assert got.name == "iris-agent"


def _check_legacy_only_requires_recovery() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-legacy-") as tmp:
        home = Path(tmp)
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        legacy.mkdir()
        _select(home, legacy)
        assert selected_owned_engine(home) is None


def _check_canonical_only() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-canon-") as tmp:
        home = Path(tmp)
        canon = home / IRIS_AGENT_CHECKOUT_NAME
        write_owned_slot_fixture(canon)
        got = iris_agent_repo_dir(home)
        assert got == canon
        assert selected_owned_engine(home) == canon


def _check_both_prefer_canonical() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-both-") as tmp:
        home = Path(tmp)
        canon = home / IRIS_AGENT_CHECKOUT_NAME
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        write_owned_slot_fixture(canon)
        legacy.mkdir()
        _select(home, legacy)
        got = iris_agent_repo_dir(home)
        assert got == canon
        assert got.name == "iris-agent"


def _check_named_recovery_slot_beats_hermes() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-slot-") as tmp:
        home = Path(tmp)
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        legacy.mkdir()
        slot = home / "iris-agent.slot-bbbbbbbbbbbbbbbb"
        write_owned_slot_fixture(slot)
        _select(home, legacy, slot)
        got = iris_agent_repo_dir(home)
        assert got == slot
        assert _OWNED_SLOT_NAME.fullmatch(got.name)


def _check_unpublished_slots_stay_unselected() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-slots-") as tmp:
        home = Path(tmp)
        older = home / "iris-agent.slot-cccccccccccccccc"
        newer = home / "iris-agent.slot-dddddddddddddddd"
        write_owned_slot_fixture(older)
        write_owned_slot_fixture(newer)
        assert selected_owned_engine(home) is None
        (home / ENGINE_SELECTION_FILE).write_text("[]", encoding="utf-8")
        assert selected_owned_engine(home) is None


def _check_slot_without_manifest_ignored() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-nomf-") as tmp:
        home = Path(tmp)
        legacy = home / LEGACY_AGENT_CHECKOUT_NAME
        legacy.mkdir()
        bare = home / "iris-agent.slot-eeeeeeeeeeeeeeee"
        bare.mkdir()
        _select(home, bare, legacy)
        assert selected_owned_engine(home) is None


def _check_selection_active_wins() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-repo-sel-") as tmp:
        home = Path(tmp)
        slot = home / "iris-agent.slot-ffffffffffffffff"
        active_python = write_owned_slot_fixture(slot)
        canon = home / IRIS_AGENT_CHECKOUT_NAME
        canon_python = write_owned_slot_fixture(canon)
        previous = home / "iris-agent.slot-1111111111111111"
        write_owned_slot_fixture(previous)
        _select(home, slot, previous)
        got = iris_agent_repo_dir(home)
        assert got == slot
        active_python.unlink()
        assert selected_owned_engine(home) == canon
        canon_python.unlink()
        assert selected_owned_engine(home) == previous
        (previous / "run_agent.py").write_text("damaged", encoding="utf-8")
        assert selected_owned_engine(home) is None


def _check_live_home() -> None:
    live = iris_agent_repo_dir()
    assert live.name in (
        IRIS_AGENT_CHECKOUT_NAME,
    ) or _OWNED_SLOT_NAME.fullmatch(live.name)
    product = iris_agent_home()
    active, _ = read_engine_selection(product)
    if active is not None and active == selected_owned_engine(product):
        assert live == active
        return
    if (product / IRIS_AGENT_CHECKOUT_NAME).is_dir():
        assert live == product / IRIS_AGENT_CHECKOUT_NAME


def _main() -> None:
    _check_empty_home_is_canonical()
    _check_legacy_only_requires_recovery()
    _check_canonical_only()
    _check_both_prefer_canonical()
    _check_named_recovery_slot_beats_hermes()
    _check_unpublished_slots_stay_unselected()
    _check_slot_without_manifest_ignored()
    _check_selection_active_wins()
    _check_live_home()
    print("iris_agent_repo_dir ok", iris_agent_repo_dir())


if __name__ == "__main__":
    _main()
