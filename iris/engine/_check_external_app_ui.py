"""Phase 4d: external MCP ui:// resource hook.

Run: .venv\\Scripts\\python.exe -m iris.engine._check_external_app_ui
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from iris.apps.directory import AppDirectory, AppDirectoryEntry, SOURCE_INSTALLED
from iris.apps.mcp_resource import read_configured_mcp_resource, resolve_ui_resource
from iris.engine.app_ui import (
    MAX_APP_UI_BYTES,
    app_ui_from_tool_meta,
    emit_app_ui_payload,
    materialize_mcp_app_resource,
)
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.window.main_window import MainWindow


_URI = "ui://weather/card"
_HTML = "<!doctype html><html><body>weather app</body></html>"
_STDIO_HTML = "<!doctype html><html><body>stdio mcp app</body></html>"


def _response(*, text: str | None = _HTML, blob: str | None = None, mime: str = "text/html;profile=mcp-app") -> dict:
    content = {"uri": _URI, "mimeType": mime}
    if text is not None:
        content["text"] = text
    if blob is not None:
        content["blob"] = blob
    return {"contents": [content]}


def main() -> None:
    with TemporaryDirectory() as raw:
        cache = Path(raw)
        path = materialize_mcp_app_resource(_URI, _response(), cache_dir=cache)
        assert path is not None and path.is_file()
        assert path.parent == cache and path.suffix == ".html"
        assert path.read_text(encoding="utf-8") == _HTML

        blob = base64.b64encode(_HTML.encode("utf-8")).decode("ascii")
        blob_path = materialize_mcp_app_resource(
            _URI,
            _response(text=None, blob=blob, mime="text/html+skybridge"),
            cache_dir=cache,
        )
        assert blob_path is not None
        assert blob_path.read_text(encoding="utf-8") == _HTML

        assert materialize_mcp_app_resource("https://example.com/app", _response(), cache_dir=cache) is None
        assert materialize_mcp_app_resource("ui:relative", _response(), cache_dir=cache) is None
        assert materialize_mcp_app_resource("ui://host/../secret", _response(), cache_dir=cache) is None
        assert materialize_mcp_app_resource(_URI, _response(mime="application/json"), cache_dir=cache) is None
        assert materialize_mcp_app_resource(_URI, _response(text="x" * (MAX_APP_UI_BYTES + 1)), cache_dir=cache) is None
        assert materialize_mcp_app_resource(_URI, {"contents": "bad"}, cache_dir=cache) is None
        assert materialize_mcp_app_resource(_URI, {"contents": [{}]}, cache_dir=cache) is None
        assert materialize_mcp_app_resource(_URI, _response(text=None, blob="not base64"), cache_dir=cache) is None

        calls: list[str] = []

        def resolver(uri: str) -> dict:
            calls.append(uri)
            return _response()

        offer = app_ui_from_tool_meta(
            {"ui": {"resourceUri": _URI}},
            default_title="Weather",
            resolver=resolver,
            cache_dir=cache,
        )
        assert offer is not None and offer.resource_uri == _URI
        assert Path(offer.html_path).read_text(encoding="utf-8") == _HTML
        assert calls == [_URI]
        payload = emit_app_ui_payload(
            {"_meta": {"ui": {"resourceUri": _URI}}},
            resolver=resolver,
            cache_dir=cache,
        )
        assert payload is not None and payload["resource_uri"] == _URI
        assert Path(payload["html_path"]).is_file()
        assert app_ui_from_tool_meta(
            {"ui": {"resourceUri": _URI}}, resolver=lambda _uri: (_ for _ in ()).throw(RuntimeError("offline"))
        ) is None
        unresolved = app_ui_from_tool_meta({"ui": {"resourceUri": _URI}}, default_title="Weather")
        assert unresolved is not None
        assert unresolved.html_path == ""
        assert unresolved.resource_uri == _URI

        local = app_ui_from_tool_meta({"ui": {"resourceUri": "app_host_ping.html"}})
        assert local is not None and Path(local.html_path).is_file()

        opened: list[tuple[str, str]] = []
        notices: list[str] = []

        class _Panel:
            _app_consent_path = cache / "consent.json"
            _app_directory = None

            def _ask_app_consent_hook(self, **kwargs) -> bool:
                return True

            def show_app_host(self, html_path: str, title: str = "앱") -> bool:
                opened.append((html_path, title))
                return True

            def show_attach_notice(self, message: str) -> None:
                notices.append(message)

            def open_ui_resource(self, resource_uri: str, title: str = "앱") -> bool:
                return ChatPanel.open_ui_resource(self, resource_uri, title=title)

            def _app_directory_store(self):
                from iris.apps.directory import AppDirectory

                store = getattr(self, "_app_directory", None)
                if store is None:
                    store = AppDirectory(cache / "directory.json")
                    self._app_directory = store
                return store

            def _app_consent_store_path(self):
                return self._app_consent_path

            def _ask_app_consent(self, **kwargs):
                return ChatPanel._ask_app_consent(self, **kwargs)

            def _ensure_app_open_consent(self, entry: object) -> bool:
                return ChatPanel._ensure_app_open_consent(self, entry)

        panel = _Panel()
        ChatPanel.set_mcp_app_resource_resolver(panel, resolver)
        entry = AppDirectoryEntry("remote", "Remote", "", _URI, SOURCE_INSTALLED)
        assert ChatPanel._open_directory_app(panel, entry)
        assert opened and opened[0][1] == "Remote"
        assert Path(opened[0][0]).read_text(encoding="utf-8") == _HTML
        assert not notices

        server = Path(__file__).resolve().parents[2] / "tests" / "iris_mcp_app_resource_server.py"
        (cache / "config.yaml").write_text(
            "mcp_servers:\n"
            "  fixture-app:\n"
            f"    command: {json.dumps(sys.executable)}\n"
            f"    args: [{json.dumps('-u')}, {json.dumps(str(server))}]\n"
            "    enabled: true\n"
            "  remote-http:\n"
            "    transport: http\n"
            "    url: https://example.com/mcp\n",
            encoding="utf-8",
        )
        resource = read_configured_mcp_resource("fixture-app", _URI, home=cache)
        assert isinstance(resource, dict)
        assert resource["contents"][0]["text"] == _STDIO_HTML
        assert read_configured_mcp_resource("missing", _URI, home=cache) is None
        assert read_configured_mcp_resource("remote-http", _URI, home=cache) is None

        directory = AppDirectory(cache / "directory.json")
        installed = directory.install(
            AppDirectoryEntry(
                "remote-stdio",
                "Remote stdio",
                "",
                _URI,
                SOURCE_INSTALLED,
                "fixture-app",
            )
        )
        assert AppDirectory(cache / "directory.json").get(installed.id).server_name == "fixture-app"

        via_directory = resolve_ui_resource(_URI, home=cache)
        assert isinstance(via_directory, dict)
        assert via_directory["contents"][0]["text"] == _STDIO_HTML

        netloc_uri = "ui://fixture-app/card"
        via_netloc = resolve_ui_resource(netloc_uri, home=cache)
        assert isinstance(via_netloc, dict)
        assert via_netloc["contents"][0]["uri"] == netloc_uri
        assert via_netloc["contents"][0]["text"] == _STDIO_HTML

        import iris.apps.mcp_resource as mcp_resource

        original = mcp_resource.read_configured_mcp_resource
        original_resolve = mcp_resource.resolve_ui_resource
        mcp_resource.read_configured_mcp_resource = lambda server_name, uri, home=None: original(
            server_name, uri, home=cache
        )
        mcp_resource.resolve_ui_resource = lambda uri, home=None: original_resolve(
            uri, home=cache
        )
        try:
            default_panel = _Panel()
            assert ChatPanel._open_directory_app(default_panel, installed)
            assert Path(opened[-1][0]).read_text(encoding="utf-8") == _STDIO_HTML

            host = type("Host", (), {})()
            host._ignore_chat_result = False
            host._chat = _Panel()
            opened.clear()
            MainWindow._on_hermes_app_ui(host, "Remote host", "", resource_uri=_URI)
            assert opened and opened[0][1] == "Remote host"
            assert Path(opened[0][0]).read_text(encoding="utf-8") == _STDIO_HTML
        finally:
            mcp_resource.read_configured_mcp_resource = original
            mcp_resource.resolve_ui_resource = original_resolve

    print("external app ui ok")


if __name__ == "__main__":
    main()
