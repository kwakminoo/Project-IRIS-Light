from __future__ import annotations

from unittest import TestCase
from unittest.mock import MagicMock

from iris.engine.types import (
    DANGEROUS_ACTIONS,
    IRIS_ENGINE_TOOLS,
    assert_dangerous_actions_confirm,
    assert_iris_engine_tools_catalog,
)
from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.project import register_project_actions


class DangerousActionsConfirmTests(TestCase):
    def test_live_registry_marks_dangerous_actions_confirm_required(self) -> None:
        registry = ActionRegistry()
        register_project_actions(MagicMock(), registry)
        assert_dangerous_actions_confirm(registry)
        for name in DANGEROUS_ACTIONS:
            spec = registry.spec(name)
            self.assertIsNotNone(spec)
            self.assertTrue(spec.confirm_required)

    def test_stripped_confirm_fails_the_boot_assert(self) -> None:
        registry = ActionRegistry()
        for name in DANGEROUS_ACTIONS:
            registry.register(name, lambda _args: {}, summary=name)
        with self.assertRaises(AssertionError) as ctx:
            assert_dangerous_actions_confirm(registry)
        self.assertIn("confirm_required", str(ctx.exception))

    def test_invoke_without_hud_is_rejected(self) -> None:
        registry = ActionRegistry()
        register_project_actions(MagicMock(), registry)
        result = registry.invoke(
            "project.write_file",
            {"rel_path": "a.py", "content": "x", "confirm": True},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "human confirm required")


class EngineToolsCatalogTests(TestCase):
    def test_iris_engine_tools_has_no_duplicates(self) -> None:
        assert_iris_engine_tools_catalog()
        self.assertEqual(len(IRIS_ENGINE_TOOLS), len(set(IRIS_ENGINE_TOOLS)))

    def test_duplicate_names_fail_the_catalog_check(self) -> None:
        with self.assertRaises(AssertionError) as ctx:
            assert_iris_engine_tools_catalog(("iris_invoke", "iris_invoke"))
        self.assertIn("duplicate", str(ctx.exception))

    def test_stdio_tool_names_match_the_single_list(self) -> None:
        from iris.mcp.iris_control_stdio import TOOLS

        names = tuple(tool["name"] for tool in TOOLS)
        self.assertEqual(names, IRIS_ENGINE_TOOLS)
        assert_iris_engine_tools_catalog(names)
