"""Product Engine.ensure_ready must apply Ollama options guard before spawn.

After Hermes absorption, chat uses InternalSidecar and never hits gateway ensure.
Unguarded ``if ollama_num_ctx: options=…`` then leaks into NVIDIA and returns HTTP 400.

Run:
  .venv\\Scripts\\python.exe -m iris.engine._check_ensure_ready_ollama_options_guard
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from iris.engine.runtime import Engine
from iris.engine.types import EngineHome, EngineReady, InternalSidecar
from iris.system.iris_agent_ollama_guard import ollama_options_guard_present

_UNGUARDED = (
    "if ollama_num_ctx:\n"
    '    extra_body["options"] = {"num_ctx": ollama_num_ctx}\n'
)


def _write_unguarded_checkout(home: Path) -> Path:
    # Absorbed live homes use iris-agent; main still documents hermes-agent.
    root = home / "iris-agent"
    custom = root / "plugins" / "model-providers" / "custom"
    custom.mkdir(parents=True)
    path = custom / "__init__.py"
    path.write_text(_UNGUARDED, encoding="utf-8", newline="\n")
    return root


def _check_ensure_ready_source_calls_guard() -> None:
    src = inspect.getsource(Engine.ensure_ready)
    assert "apply_ollama_options_guard" in src or "_apply_ollama_options_guard" in src, (
        "ensure_ready must apply ollama options guard on the product path"
    )


def _check_ensure_ready_patches_missing_guard_before_spawn() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-eng-guard-") as td:
        home = Path(td)
        checkout = _write_unguarded_checkout(home)
        assert not ollama_options_guard_present(checkout)

        fake = MagicMock()
        fake.poll.return_value = None
        fake.pid = 4242
        engine = Engine(InternalSidecar(home=EngineHome(home)))

        with (
            patch("iris.engine.runtime.probe_engine_python", return_value=None),
            patch(
                "iris.engine.runtime._spawn_sidecar",
                return_value=(fake, 4242),
            ) as spawn,
            patch("iris.engine.runtime.install_into"),
        ):
            result = engine.ensure_ready()

        assert isinstance(result, EngineReady), result
        spawn.assert_called_once()
        assert ollama_options_guard_present(checkout), (
            "ensure_ready must soft-patch custom provider before spawn"
        )


def _check_live_child_restarts_when_guard_just_applied() -> None:
    with tempfile.TemporaryDirectory(prefix="iris-eng-guard-live-") as td:
        home = Path(td)
        checkout = _write_unguarded_checkout(home)
        assert not ollama_options_guard_present(checkout)

        old = MagicMock(name="old_child")
        old.poll.return_value = None
        old.pid = 111
        new = MagicMock(name="new_child")
        new.poll.return_value = None
        new.pid = 222

        engine = Engine(InternalSidecar(home=EngineHome(home)))
        engine._child = old
        engine._child_hello_pid = 111

        with (
            patch("iris.engine.runtime.probe_engine_python", return_value=None),
            patch(
                "iris.engine.runtime._spawn_sidecar",
                return_value=(new, 222),
            ) as spawn,
            patch("iris.engine.runtime.install_into"),
            patch.object(engine, "_forget_child") as forget,
        ):

            def _forget() -> None:
                engine._child = None
                engine._child_hello_pid = None

            forget.side_effect = _forget
            result = engine.ensure_ready()

        assert isinstance(result, EngineReady), result
        forget.assert_called()
        spawn.assert_called_once()
        assert ollama_options_guard_present(checkout)
        assert engine._child is new


def main() -> None:
    _check_ensure_ready_source_calls_guard()
    _check_ensure_ready_patches_missing_guard_before_spawn()
    _check_live_child_restarts_when_guard_just_applied()
    print("ensure_ready_ollama_options_guard ok")


if __name__ == "__main__":
    main()
