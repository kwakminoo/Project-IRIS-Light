"""Check engine updates against the packaged manifest without a Git checkout."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from iris.system.iris_agent_install import vendor_iris_agent_core_root, verify_owned_core_source
from iris.system.iris_agent_update import check_iris_agent_update


def _main() -> None:
    bundle = vendor_iris_agent_core_root()
    current = check_iris_agent_update(repo=bundle)
    assert not current.available and current.local_sha == current.remote_sha, current
    with tempfile.TemporaryDirectory(prefix="iris-owned-update-") as tmp:
        legacy = Path(tmp) / "hermes-agent"
        legacy.mkdir()
        status = check_iris_agent_update(repo=legacy)
        assert status.available == verify_owned_core_source(bundle)["legacy_migration_approved"]
        (legacy / "SOURCE_MANIFEST.json").write_text(json.dumps({"package": "broken"}), encoding="utf-8")
        assert check_iris_agent_update(repo=legacy).available
        assert not check_iris_agent_update(repo=Path(tmp) / "missing").available
    print("iris_agent_update check ok")


if __name__ == "__main__":
    _main()
