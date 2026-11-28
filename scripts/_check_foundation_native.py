"""Live, temporary Speak capability exercising the product Native dispatcher."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from scripts.validate_wave17 import MODEL, write_json


ACTION = "foundation.sample_stamp"
MODEL_NAME = "foundation_sample_stamp"


def with_fixture():
    from iris.infrastructure import speak_capability as speak

    grant = speak.SpeakGrant(ACTION, speak.ExecKind.SURFACE, "Get a fresh foundation sample stamp",
                             {"type": "object", "properties": {"sample": {"type": "string", "enum": ["cerulean"]}},
                              "required": ["sample"], "additionalProperties": False})
    return replace(speak.PHASE4_ALLOWLIST, grants=(*speak.PHASE4_ALLOWLIST.grants, grant))


def run(out: Path) -> None:
    from iris.engine import CancelToken, ChatTranscript, Engine, EngineHome, InternalSidecar, StatelessTurn, TurnFinished, runtime
    from iris.engine._home import engine_python
    from iris.infrastructure import speak_capability as speak
    from iris.infrastructure.agent_runtime import iris_agent_home
    from iris.infrastructure.iris_agent_client import resolve_iris_agent_inference
    from iris.system.control_surface import ActionRegistry, MainThreadInvoker
    from iris.system.execution_context import ExecutionContext, bind_host_tool_call_meta, host_tool_call_meta

    home = out / "agent"
    home.mkdir()
    (home / "config.yaml").write_text("agent:\n  tool_choice: auto\nmodel:\n  ollama_num_ctx: 64000\n", encoding="utf-8")
    py = engine_python(EngineHome(iris_agent_home()))
    assert py is not None, "Owned Core Python unavailable"
    sidecar = out / "sidecar_fixture.py"
    sidecar.write_text(
        f"import runpy, sys\nsys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
        "from scripts._check_foundation_native import with_fixture\n"
        "from iris.infrastructure import speak_capability as speak\n"
        "speak.PHASE4_ALLOWLIST = with_fixture()\n"
        f"runpy.run_path({str(runtime._SIDECAR_MAIN)!r}, run_name='__main__')\n", encoding="utf-8",
    )
    registry = ActionRegistry()
    marker = "CERULEAN" + uuid4().hex[:12]
    approvals, calls = [], []

    def handler(args):
        calls.append(host_tool_call_meta())
        return {"sample": args["sample"], "stamp": marker}

    def approve(spec, args):
        approvals.append({"action": spec.name, "risk": spec.risk, "args": dict(args)})
        return spec.name == ACTION and spec.risk == "high" and args == {"sample": "cerulean"}

    registry.register(ACTION, handler, summary="Foundation sample", risk="high", confirm_required=True)
    context = ExecutionContext(session_id="foundation-native", source="desktop")
    target = replace(resolve_iris_agent_inference(MODEL, ollama_base_url="http://127.0.0.1:11434/v1"), api_key="ollama")
    engine = Engine(InternalSidecar(home=EngineHome(home)), staged_python=py)
    engine.bind_tool_handler(lambda action, args: speak.default_speak_tools().invoke(action, args).as_dict())
    invoker = MainThreadInvoker()
    invoker.bind(lambda action, _timeout: action())
    speak.bind_live_control_surface(SimpleNamespace(registry=registry, invoker=invoker, booting=False))
    try:
        with patch.object(speak, "PHASE4_ALLOWLIST", with_fixture()), patch.object(runtime, "_SIDECAR_MAIN", sidecar), \
                patch.object(runtime, "_WATCH_LOG", home / "host-watch.log"):
            assert MODEL_NAME in {row.model_name for row in speak.engine_tool_bindings("home")}
            with bind_host_tool_call_meta(execution_context=context):
                assert not speak.default_speak_tools().invoke(ACTION, {"sample": "cerulean"}).ok
            registry.set_human_confirm(approve)
            invalid = speak.default_speak_tools().invoke(ACTION, {"sample": 5})
            assert invalid.error_code == "invalid_arguments"
            with bind_host_tool_call_meta(execution_context=context, cancelled=lambda: True):
                assert not speak.default_speak_tools().invoke(ACTION, {"sample": "cerulean"}).ok
            assert not calls and not approvals
            turn = StatelessTurn(ChatTranscript.parse([{"role": "user", "content":
                "Use tool_describe to load foundation_sample_stamp, then use tool_call to request the "
                "fresh foundation sample stamp with sample cerulean. Reply with the exact stamp alone.",
            }]), target, CancelToken(), execution_context=context)
            terminal = list(engine.run_turn(turn))[-1]
    finally:
        engine.shutdown()
        speak.bind_live_control_surface(None)
    assert MODEL_NAME not in {row.model_name for row in speak.engine_tool_bindings("home")}
    assert not speak.default_speak_tools().invoke(ACTION, {"sample": "cerulean"}).ok
    assert speak.default_speak_tools().invoke("ping", {}).ok
    answer = terminal.text.strip() if isinstance(terminal, TurnFinished) else ""
    proof = {"model": MODEL, "terminal": type(terminal).__name__, "answer": answer, "marker": marker,
             "approvals": approvals, "correlation": calls, "fixture_removed": True}
    write_json(out / "foundation-native.json", proof)
    assert answer == marker and len(approvals) == len(calls) == 1 and all(calls[0]), proof
