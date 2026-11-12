"""Unit 2 — Product engine source is InternalSidecar only.

Fails when parse_engine_source / settings / env can reopen ExternalGateway
as the product default. Phase 5 in-process merge stays out of scope.

Run:
  .venv\\Scripts\\python.exe -m iris.engine._check_iris_agent_sidecar_only
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def _check_parse_ignores_external_flag() -> None:
    from iris.engine.types import InternalSidecar, parse_engine_source

    flagged = SimpleNamespace(
        hermes_external_gateway=True,
        hermes_base_url="http://127.0.0.1:8642/v1",
        hermes_api_key="k",
    )
    source = parse_engine_source(flagged)
    assert isinstance(source, InternalSidecar), type(source)


def _check_env_cannot_reopen_external() -> None:
    from iris.engine.runtime import _settings_from_env
    from iris.engine.types import InternalSidecar, parse_engine_source

    with patch.dict(
        os.environ,
        {
            "IRIS_HERMES_EXTERNAL_GATEWAY": "1",
            "IRIS_HERMES_BASE_URL": "http://127.0.0.1:8642/v1",
            "IRIS_HERMES_API_KEY": "env-key",
        },
        clear=False,
    ):
        source = parse_engine_source(_settings_from_env())
    assert isinstance(source, InternalSidecar), type(source)


def _check_engine_source_type_is_sidecar_only() -> None:
    from iris.engine import types as t

    assert t.EngineSource is t.InternalSidecar
    assert not hasattr(t, "ExternalGateway")


def _check_settings_has_no_external_product_flag() -> None:
    from iris.config.settings import Settings

    assert not hasattr(Settings, "hermes_external_gateway")
    settings_src = (ROOT / "iris" / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    assert "hermes_external_gateway" not in settings_src
    assert "IRIS_HERMES_EXTERNAL_GATEWAY" not in settings_src


def _check_product_workers_have_no_external_branch() -> None:
    path = ROOT / "iris" / "ui" / "workers" / "iris_agent_workers.py"
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert "_run_external" not in names
    assert "_ensure_gateway" not in names
    assert "ExternalGateway" not in text


def main() -> None:
    _check_parse_ignores_external_flag()
    _check_env_cannot_reopen_external()
    _check_engine_source_type_is_sidecar_only()
    _check_settings_has_no_external_product_flag()
    _check_product_workers_have_no_external_branch()
    print("iris_agent_sidecar_only ok")


if __name__ == "__main__":
    main()
