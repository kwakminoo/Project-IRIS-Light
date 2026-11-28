"""WAVE 1.7 FRC-01: adaptive context budget + compact tool surface."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from iris.engine.tool_surface import assemble_iris_model_tools, dispatch_iris_bridge


def _schema(name, description, **metadata):
    return {
        "type": "function",
        "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
        **metadata,
    }


class TestWave17AdaptiveContext(unittest.TestCase):
    def test_small_context_keeps_relevant_schemas_and_defers_the_rest(self):
        native = [_schema("search_files", "Find files by filename"), _schema("local_read_file", "Read a file")]
        unrelated = [_schema(f"mcp_other_{i}", "Unrelated workflow " * 300, source="mcp", source_name="other")
                     for i in range(10)]
        service = _schema("mcp_iridium_code", "Get iridium validation code", source="mcp", source_name="iridium")
        discarded = _schema("settings_get", "Get settings " * 400)
        visible, deferred, active = assemble_iris_model_tools(
            [discarded, *unrelated, service, *native, service],
            context_length=4096, user_message="Find an inventory file and get an iridium validation code.",
        )
        names = [tool["function"]["name"] for tool in visible]
        self.assertTrue({"search_files", "local_read_file", "mcp_iridium_code", "tool_search"} <= set(names))
        self.assertEqual(names.count("mcp_iridium_code"), 1)
        self.assertNotIn("settings_get", names)
        self.assertLessEqual(len(json.dumps(visible, ensure_ascii=False).encode()), (4096 // 5) * 3)
        result = json.loads(dispatch_iris_bridge("tool_search", {"queries": ["mcp_other_5"]}, deferred_defs=deferred))
        self.assertEqual(result["results"][0]["matches"][0], "mcp_other_5")

    def test_ollama_context_distinguishes_model_limit_loaded_window_and_request_policy(self):
        from iris.infrastructure.ollama_client import OllamaClient

        client = OllamaClient()
        metadata = {"capabilities": ["completion", "tools"], "model_info": {"example.context_length": 131072}}
        with (
            patch.object(client, "show_model", lambda *_args, **_kwargs: metadata),
            patch.object(client, "_get_json", lambda _path, **_kwargs: {
                "models": [{"name": "example:latest", "context_length": 12288}],
            }),
        ):
            maximum, loaded, budget, tools = client.openai_context_budget("example")
            self.assertEqual((maximum, loaded, budget, tools), (131072, 12288, 4096, True))
            metadata["parameters"] = "temperature 0.5\nnum_ctx 8192"
            self.assertEqual(client.openai_context_budget("example"), (131072, 12288, 8192, True))
            self.assertEqual(
                client.openai_context_budget("example", requested=16384), (131072, 12288, 16384, True),
            )
            self.assertEqual(client.openai_context_budget("example", requested=200000)[2], 131072)
            metadata["capabilities"] = ["completion"]
            self.assertIs(client.openai_context_budget("example")[-1], False)

    def test_tool_schema_budget_respects_space_left_by_messages(self):
        tool = _schema("search_files", "Find a file")
        visible, deferred, bridge = assemble_iris_model_tools(
            [tool], context_length=4096, available_tokens=0,
        )
        self.assertEqual(visible, [])
        self.assertEqual(deferred, [tool])
        self.assertFalse(bridge)

    def test_mixed_local_file_and_mcp_prefer_their_own_bindings(self):
        visible, _, _ = assemble_iris_model_tools(
            [_schema("read_file", "Read an IDE project file"), _schema("content_extract", "Extract a document"),
             _schema("local_read_file", "Read a local file"), _schema("search_files", "Find local files"),
             _schema("mcp_iridium", "Get validation code", source="mcp", source_name="iridium")],
            context_length=8192, user_message="Read the local file C:/fixture.txt and ask the iridium validation service.",
        )
        names = [tool["function"]["name"] for tool in visible]
        self.assertEqual(names[:2], ["mcp_iridium", "local_read_file"])
        self.assertNotIn("read_file", names)

    def test_context_overflow_prunes_history_before_the_current_tool_loop(self):
        from iris.engine._sidecar_main import _prune_request_history

        system = {"role": "system", "content": "Trusted policy"}
        previous = [{"role": "user", "content": "Old request"}, {"role": "assistant", "content": "Old reply"}]
        current = [{"role": "user", "content": "Current task"},
                   {"role": "assistant", "tool_calls": [{"id": "current-call"}]},
                   {"role": "tool", "tool_call_id": "current-call", "content": "Actual result"}]
        messages = [system, *previous, *current]
        self.assertEqual(_prune_request_history(messages, len, 4), [system, *current])
        self.assertEqual(_prune_request_history(messages, len, 8), messages)

    def test_unreachable_ollama_is_reported_before_core_initialization(self):
        from urllib.error import URLError

        from iris.engine import _sidecar_main as sidecar

        with (patch.object(sidecar, "_local_ollama_probe", side_effect=URLError("offline")),
              patch.object(sidecar, "_fail") as fail):
            sidecar._run_agent_turn(None, [], "Test connection", {})
        fail.assert_called_once_with("model_connection", "Ollama model lookup could not connect")

    def test_model_without_tools_cannot_dispatch_native_bindings(self):
        import sys
        from types import SimpleNamespace

        from iris.engine import _sidecar_main as sidecar

        model_tools = SimpleNamespace()
        agent = SimpleNamespace()
        client = SimpleNamespace(openai_context_budget=lambda *_args, **_kwargs: (32768, 4096, 4096, False))
        with (patch.dict(sys.modules, {"model_tools": model_tools}),
              patch.object(sidecar, "_guard_native_tool_refresh"),
              patch.object(sidecar, "_guard_hermes_registry_dispatch"),
              patch.object(sidecar, "_request_native_tool") as dispatch):
            names = sidecar._install_iris_engine_tools(agent, ollama_probe=(client, {"capabilities": ["completion"]}))
            self.assertEqual(names, ())
            self.assertEqual(agent.tools, [])
            self.assertIn("cannot call tools", agent.ephemeral_system_prompt)
            self.assertFalse(json.loads(model_tools.handle_function_call("terminal", {"command": "echo probe"}))["ok"])
        dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
