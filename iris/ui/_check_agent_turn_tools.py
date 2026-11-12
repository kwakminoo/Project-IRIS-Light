"""Hermes가 켜져 있으면 채팅 의도 6종은 모델 도구로 간다.

  .venv\\Scripts\\python.exe -m iris.ui._check_agent_turn_tools
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from iris.engine.runtime import Engine
from iris.engine.types import EngineHome, InternalSidecar
from iris.infrastructure.agent_tool_registry import speak_invoke_agent_tool
from iris.infrastructure.speak_capability import (
    bind_live_control_surface,
    engine_tool_action,
    engine_tool_schemas,
)
from iris.knowledge.pdf_export import verify_pdf_file
from iris.runtime.agent_local_gate import hermes_owns_local_intents
from iris.ui._check_control_action_split import _surface


def main() -> None:
    assert hermes_owns_local_intents(True) is True
    assert hermes_owns_local_intents(False) is False

    window, reg = _surface()
    names = {item["name"] for item in reg.catalog()}
    for name in ("note.export_pdf", "extension.install_github", "project.write_image_code"):
        assert name in names, name

    missing_content = reg.invoke("note.export_pdf", {})
    assert missing_content["ok"] is False
    assert "content" in missing_content["error"]

    missing_url = reg.invoke("extension.install_github", {})
    assert missing_url["ok"] is False
    assert "url" in missing_url["error"]

    missing_image = reg.invoke("project.write_image_code", {})
    assert missing_image["ok"] is False
    assert "image" in missing_image["error"]

    missing_file = reg.invoke(
        "project.write_image_code",
        {"image": "C:/no/such-iris-image.png", "rel_path": "a.py"},
    )
    assert missing_file["ok"] is False
    assert "image" in missing_file["error"]

    schemas = engine_tool_schemas()
    assert all("." not in row["name"] for row in schemas)
    assert engine_tool_action("settings_get") == "settings.get"
    pdf_schema = next(row for row in schemas if row["name"] == "note_export_pdf")
    assert pdf_schema["parameters"]["properties"]["path"]["type"] == "string"
    assert pdf_schema["parameters"]["anyOf"]

    # PEV/V: host bridge -> real ActionRegistry -> child PDF writer -> actual file bytes.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "bridge-check.pdf"
        window._current_project_root.return_value = tmp
        sink = io.StringIO()
        child = SimpleNamespace(stdin=sink)
        engine = Engine(InternalSidecar(EngineHome(Path(tmp))))
        bind_live_control_surface(SimpleNamespace(registry=reg, booting=False))
        engine.bind_tool_handler(speak_invoke_agent_tool)
        try:
            engine._reply_to_tool_request(
                child,
                {
                    "id": "pdf-v",
                    "name": "note.export_pdf",
                    "args": {"content": "IRIS PDF bridge verification", "path": str(target)},
                },
            )
        finally:
            bind_live_control_surface(None)
        reply = json.loads(sink.getvalue())
        result = reply["result"]
        assert result["ok"] is True, result
        actual = Path(result["data"]["path"])
        assert actual == target.resolve()
        assert result["data"]["verified"] is True
        assert verify_pdf_file(actual)["ok"] is True
        assert window._turn_write_path == str(actual)
    print("agent turn tools ok")


if __name__ == "__main__":
    main()
