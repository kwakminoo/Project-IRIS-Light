"""L6 live core lifecycle in an isolated home with an installed local Ollama model."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path


def main() -> None:
    evidence_dir = Path(".tmp/wave16-lifecycle").resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="run-", dir=evidence_dir))
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[key] = str(home)
    os.environ["IRIS_AGENT_HOME"] = str(home / "agent")
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ.pop("IRIS_ENGINE_AGENT_MODULE", None)
    os.environ["PATH"] = os.pathsep.join(
        entry for entry in os.environ["PATH"].split(os.pathsep)
        if not any(part.lower().startswith("hermes") for part in Path(entry).parts)
    )

    from iris.engine import CancelToken, ChatTranscript, Engine, EngineHome, EngineReady, InternalSidecar, StatelessTurn, TurnFinished
    from iris.engine._home import checkout_python, probe_engine_python
    from iris.infrastructure.agent_runtime import iris_agent_home, read_engine_selection, selected_owned_engine
    from iris.infrastructure.iris_agent_client import resolve_iris_agent_inference
    from iris.system import iris_agent_install as install

    agent = iris_agent_home()
    engine_home = EngineHome(agent)
    source = InternalSidecar(home=engine_home)
    target = resolve_iris_agent_inference("gpt-oss:20b")
    results = {}
    print(f"Isolated evidence directory: {home}", flush=True)

    def record(label: str, **details: object) -> None:
        results[label] = details
        (home / "evidence.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(label, details, flush=True)

    def model_turn(label: str, staged: Path | None = None) -> None:
        python = checkout_python(staged) if staged is not None else None
        if staged is not None and python is None:
            raise RuntimeError("Staged engine Python is missing")
        engine = Engine(source, staged_python=python)
        marker = "IRIS-ACF-HELLO"
        start = time.perf_counter()
        try:
            ready = engine.ensure_ready()
            if not isinstance(ready, EngineReady):
                raise RuntimeError(f"Owned engine did not start: {ready}")
            startup = time.perf_counter() - start
            turn = StatelessTurn(
                ChatTranscript.parse([{"role": "user", "content": f"Reply with just this exact text: {marker}"}]),
                target, CancelToken(), session_id=f"lifecycle-{label}",
            )
            events = list(engine.run_turn(turn))
            terminal = events[-1] if events else None
            answer = terminal.text.strip() if isinstance(terminal, TurnFinished) else ""
            if answer != marker:
                raise RuntimeError(
                    f"Local model response mismatched: terminal={type(terminal).__name__}, "
                    f"length={len(answer)}, contains_marker={marker in answer}"
                )
        finally:
            engine.shutdown()
        record(label, marker=marker, startup_sec=round(startup, 2), total_sec=round(time.perf_counter() - start, 2))

    assert selected_owned_engine(agent) is None
    assert not (agent / "hermes-agent").exists()
    assert shutil.which("hermes") is None
    first = install.install_iris_agent_with_system_python(home=agent, on_stream=lambda s: print(s, flush=True))
    assert first.ok, first.message
    initial, previous = read_engine_selection(agent)
    assert initial is not None and previous is None
    assert probe_engine_python(engine_home) is None
    (agent / "config.yaml").write_text("model:\n  ollama_num_ctx: 64000\n", encoding="utf-8")
    manifest = install.verify_owned_core_source(initial)
    record("install", slot=initial.name, version=manifest["version"], sha=manifest["upstream_revision"])
    model_turn("first")

    data = agent / "lifecycle-user-data.txt"
    data.write_text("preserve", encoding="utf-8")
    updated = install.install_iris_agent_with_system_python(
        home=agent, update=True, model_check=lambda slot: model_turn("candidate", staged=slot),
        on_stream=lambda s: print(s, flush=True),
    )
    assert updated.ok, updated.message
    active, previous = read_engine_selection(agent)
    assert active is not None and active != initial and previous == initial
    assert selected_owned_engine(agent) == active
    record("update", slot=active.name, previous=initial.name)
    model_turn("updated")

    (active / "run_agent.py").write_text("# simulated damage in the isolated slot", encoding="utf-8")
    assert selected_owned_engine(agent) == initial
    assert install.rollback_iris_agent(agent) == initial.name
    assert selected_owned_engine(agent) == initial
    assert data.read_text(encoding="utf-8") == "preserve"
    assert not (agent / "hermes-agent").exists()
    model_turn("rollback")
    record("recovery", slot=initial.name, preserved_user_data=True, reference_present=False)


if __name__ == "__main__":
    main()
