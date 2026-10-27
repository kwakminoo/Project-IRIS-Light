"""sync_iris_control home= writes the given tree, not the user Hermes tree."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import yaml

from iris.system.hermes_iris_control_sync import sync_iris_control


def _assert_no_sync_artifacts(root: Path) -> None:
    assert not (root / "config.yaml").exists()
    assert not (root / "skills").exists()
    assert not (root / "SOUL.md").exists()
    assert not (root / "memories").exists()


def _assert_synced(home: Path) -> None:
    config = home / "config.yaml"
    assert config.is_file(), config
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    servers = data.get("mcp_servers") or {}
    assert "iris-control" in servers
    disabled = (data.get("agent") or {}).get("disabled_toolsets") or []
    names = [str(x).strip() for x in disabled]
    assert "terminal" in names
    assert "browser" in names
    skill = home / "skills" / "iris-control" / "iris-browser" / "SKILL.md"
    assert skill.is_file(), skill


class SyncIrisControlHomeTests(TestCase):
    def test_explicit_home_writes_tmp_not_user_hermes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "engine"
            sentinel = root / "hermes-sentinel"
            sentinel.mkdir()
            with (
                patch(
                    "iris.system.hermes_iris_control_sync.hermes_home",
                    return_value=sentinel,
                ),
                patch(
                    "iris.system.hermes_soul_sync.hermes_home",
                    return_value=sentinel,
                ),
                patch(
                    "iris.system.hermes_memory_nudge.hermes_home",
                    return_value=sentinel,
                ),
            ):
                report = sync_iris_control(home=home, reconnect_gateway=False)
            self.assertTrue(report.mcp_installed)
            _assert_synced(home)
            _assert_no_sync_artifacts(sentinel)

    def test_default_sync_uses_hermes_home(self) -> None:
        with TemporaryDirectory() as tmp:
            fake = Path(tmp) / "hermes"
            with (
                patch(
                    "iris.system.hermes_iris_control_sync.hermes_home",
                    return_value=fake,
                ),
                patch(
                    "iris.system.hermes_soul_sync.hermes_home",
                    return_value=fake,
                ),
                patch(
                    "iris.system.hermes_memory_nudge.hermes_home",
                    return_value=fake,
                ),
            ):
                report = sync_iris_control(reconnect_gateway=False)
            self.assertTrue(report.mcp_installed)
            _assert_synced(fake)
