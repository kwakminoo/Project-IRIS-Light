from types import SimpleNamespace

from iris.system.control_surface import ActionRegistry
from iris.ui.chat import skill_mcp_dialogs
from iris.ui.control_actions.learning import register_learning_actions


def test_registered_skill_can_be_listed_and_read_without_arbitrary_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_mcp_dialogs, "iris_agent_root", lambda: tmp_path)
    md = skill_mcp_dialogs.add_custom_skill("demo", "Read the validated test fixture")
    (md.parent / "guide.md").write_text("local guide body", encoding="utf-8")
    (md.parent.parent / "secret.md").write_text("outside the skill", encoding="utf-8")
    registry = ActionRegistry()
    register_learning_actions(SimpleNamespace(), registry)

    listed = registry.invoke("skill.list", {})
    assert listed["result"]["skills"][0]["name"] == "demo"
    response = registry.invoke("skill.view", {"name": "demo"})
    assert "validated test fixture" in response["result"]["text"]
    assert str(tmp_path) not in str(response)
    guide = registry.invoke("skill.view", {"name": "demo", "resource": "guide.md"})
    assert "local guide body" in guide["result"]["text"]
    assert not registry.invoke("skill.view", {"name": "demo", "resource": "../secret.md"})["ok"]


def test_skill_management_shares_profile_and_requires_human_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_mcp_dialogs, "iris_agent_root", lambda: tmp_path)
    monkeypatch.setattr(skill_mcp_dialogs, "_sync_wiki_catalog", lambda: None)
    registry = ActionRegistry()
    register_learning_actions(SimpleNamespace(), registry)
    create = {"operation": "create", "name": "demo", "text": "original skill"}
    assert not registry.invoke("skill.manage", {**create, "confirm": True})["ok"]
    registry.set_human_confirm(lambda _spec, _args: True)
    assert registry.invoke("skill.manage", create)["ok"]
    assert not registry.invoke("skill.manage", create)["ok"]
    assert registry.invoke("skill.manage", {"operation": "disable", "name": "demo"})["ok"]
    assert not skill_mcp_dialogs.list_iris_agent_skills()
    assert registry.invoke("skill.manage", {"operation": "enable", "name": "demo"})["ok"]
    assert registry.invoke("skill.manage", {"operation": "update", "name": "demo", "text": "new operation"})["ok"]
    assert "new operation" in registry.invoke("skill.view", {"name": "demo"})["result"]["text"]
    assert registry.invoke("skill.manage", {"operation": "remove", "name": "demo"})["ok"]
    assert not skill_mcp_dialogs.list_iris_agent_skills()
    assert list((tmp_path / "archived-skills").glob("*/SKILL.md"))
