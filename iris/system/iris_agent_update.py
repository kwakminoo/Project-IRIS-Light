"""Update the active engine from the IRIS application bundle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from iris.engine.runtime import verify_engine_model
from iris.infrastructure.agent_runtime import iris_agent_home, iris_agent_repo_dir
from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.system.iris_agent_install import (
    install_iris_agent_with_system_python,
    vendor_iris_agent_core_root,
    verify_owned_core_source,
)


@dataclass(frozen=True)
class IrisAgentUpdateStatus:
    available: bool
    local_sha: str = ""
    remote_sha: str = ""
    detail: str = ""
    repo: str = ""


def check_iris_agent_update(*, repo: Path | None = None) -> IrisAgentUpdateStatus:
    root = repo if repo is not None else iris_agent_repo_dir(iris_agent_home())
    bundle = vendor_iris_agent_core_root()
    if not root.is_dir():
        return IrisAgentUpdateStatus(False, detail="Iris Agent 미설치")
    target = verify_owned_core_source(bundle, bundled=True)
    target_sha = hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
    if not (root / "SOURCE_MANIFEST.json").is_file():
        approved = target.get("legacy_migration_approved") is True
        return IrisAgentUpdateStatus(approved, remote_sha=target_sha, detail=f"Iris Agent {target['version']}", repo=str(root))
    try:
        current = verify_owned_core_source(root)
    except (OSError, ValueError, KeyError, TypeError):
        return IrisAgentUpdateStatus(True, remote_sha=target_sha, detail="Iris Agent 설치 복구", repo=str(root))
    current_sha = hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()
    detail = "최신" if current_sha == target_sha else f"{current['version']} → {target['version']}"
    return IrisAgentUpdateStatus(current_sha != target_sha, current_sha, target_sha, detail, str(root))



def apply_iris_agent_update(
    *, target: IrisAgentInferenceTarget, on_progress: Callable[[str], None] | None = None,
) -> str:
    home = iris_agent_home()
    if not check_iris_agent_update(repo=iris_agent_repo_dir(home)).available:
        return "Iris Agent 업데이트가 없습니다."
    result = install_iris_agent_with_system_python(
        home=home, update=True, on_stream=on_progress,
        model_check=lambda slot: verify_engine_model(slot, target),
    )
    if not result.ok:
        raise RuntimeError(result.message)
    return result.message
