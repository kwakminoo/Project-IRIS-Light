"""Unit 2 — familiar OpenAI args → Control action + args by speak_surface.

Pure adapter asserts (no live NVIDIA / Control HTTP).
"""

from __future__ import annotations

from iris.engine.model_tool_names import adapt_control_invoke, as_model_surface


def check_home_dispatch() -> None:
    action, args = adapt_control_invoke(
        "write_file", "home", {"path": "C:/tmp/a.txt", "content": "hi"}
    )
    assert action == "local.write_file"
    assert args == {"path": "C:/tmp/a.txt", "content": "hi"}

    action, args = adapt_control_invoke("read_file", "home", {"path": "C:/tmp/a.txt"})
    assert action == "local.read_file"
    assert args == {"path": "C:/tmp/a.txt"}

    action, args = adapt_control_invoke(
        "search_files",
        "home",
        {"path": "C:/tmp", "pattern": "note"},
    )
    assert action == "local.search_files"
    assert args == {"root": "C:/tmp", "query": "note"}

    action, args = adapt_control_invoke(
        "terminal", "home", {"command": "echo hi", "cwd": "C:/Users/x"}
    )
    assert action == "shell.run"
    assert args == {"command": "echo hi", "cwd": "C:/Users/x"}

    action, args = adapt_control_invoke(
        "web_search", "home", {"query": "iris", "limit": 3}
    )
    assert action == "web.run_search"
    assert args == {"query": "iris", "limit": 3}

    action, args = adapt_control_invoke(
        "web_extract", "home", {"urls": ["https://example.com"], "char_limit": 1000}
    )
    assert action == "web.run_extract"
    assert args == {"urls": ["https://example.com"], "char_limit": 1000}

    action, args = adapt_control_invoke(
        "execute_code", "home", {"code": "print(1)", "timeout": 8}
    )
    assert action == "chat.exec_python"
    assert args == {"code": "print(1)", "timeout_s": 8}


def check_ide_dispatch() -> None:
    action, args = adapt_control_invoke(
        "write_file", "ide", {"path": "src/a.py", "content": "x=1\n"}
    )
    assert action == "project.write_file"
    assert args == {"rel_path": "src/a.py", "content": "x=1\n"}

    action, args = adapt_control_invoke("read_file", "ide", {"path": "src/a.py"})
    assert action == "project.read_file"
    assert args == {"rel_path": "src/a.py"}

    action, args = adapt_control_invoke(
        "search_files", "ide", {"query": "main", "limit": 10}
    )
    assert action == "project.list_files"
    assert args == {"query": "main", "limit": 10}

    action, args = adapt_control_invoke("terminal", "ide", {"command": "pytest"})
    assert action == "project.run"
    assert args == {"command": "pytest"}

    action, args = adapt_control_invoke("web_search", "ide", {"query": "docs"})
    assert action == "web.run_search"
    assert args == {"query": "docs"}

    action, args = adapt_control_invoke(
        "web_extract", "ide", {"urls": ["https://example.com/a"]}
    )
    assert action == "web.run_extract"
    assert args == {"urls": ["https://example.com/a"]}

    action, args = adapt_control_invoke(
        "execute_code", "ide", {"source": "y=2", "timeout_s": 12}
    )
    assert action == "chat.exec_python"
    assert args == {"code": "y=2", "timeout_s": 12}


def check_surface_aliases() -> None:
    assert as_model_surface("ide_companion") == "ide"
    assert as_model_surface("companion") == "ide"
    action, _ = adapt_control_invoke(
        "write_file", as_model_surface("ide_companion"), {"path": "a.py", "content": ""}
    )
    assert action == "project.write_file"
    action, _ = adapt_control_invoke(
        "terminal", as_model_surface("home"), {"command": "dir"}
    )
    assert action == "shell.run"


def check_sidecar_wires_adapter() -> None:
    from pathlib import Path

    src = Path(__file__).with_name("_sidecar_main.py").read_text(encoding="utf-8")
    assert "adapt_control_invoke" in src
    assert '_load_local_helper("model_tool_names")' in src
    assert "from iris.engine.model_tool_names" not in src


def main() -> None:
    check_home_dispatch()
    check_ide_dispatch()
    check_surface_aliases()
    check_sidecar_wires_adapter()
    print("model_tool_surface_dispatch ok")


if __name__ == "__main__":
    main()
