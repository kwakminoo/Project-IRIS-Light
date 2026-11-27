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
            metadata["capabilities"] = ["completion"]
            self.assertIs(client.openai_context_budget("example")[-1], False)


if __name__ == "__main__":
    unittest.main()
