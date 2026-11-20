"""Unit 3: @app:<id> mention parse / resolve.

Run: .venv\\Scripts\\python.exe -m iris.apps._check_app_mention
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from iris.apps.directory import AppDirectory, AppDirectoryEntry, SOURCE_INSTALLED
from iris.apps.mention import (
    AppMention,
    active_app_mention_span,
    apply_app_mention,
    mention_candidates,
    parse_app_mentions,
    resolve_app_mentions,
)


def main() -> None:
    text = "열어줘 @app:demo-ping 그리고 @app:demo-ping 다시"
    assert parse_app_mentions(text) == ["demo-ping"]
    assert AppMention(id="demo-ping").id == "demo-ping"

    mixed = "파일 @path/foo.py 와 @app:demo-ping @app:no-such"
    assert parse_app_mentions(mixed) == ["demo-ping", "no-such"]

    with TemporaryDirectory() as raw:
        root = Path(raw)
        store = AppDirectory(root / "directory.json")
        resolved = resolve_app_mentions(mixed, store)
        assert [e.id for e in resolved] == ["demo-ping"]
        assert resolve_app_mentions("@app:ghost", store) == []

        store.install(
            AppDirectoryEntry(
                id="weather",
                title="Weather",
                summary="forecast",
                resource_uri="weather.html",
                source=SOURCE_INSTALLED,
            )
        )
        hits = mention_candidates(store, "weath")
        assert [e.id for e in hits] == ["weather"]
        all_rows = mention_candidates(store, "")
        assert {e.id for e in all_rows} >= {"demo-ping", "weather"}

    assert active_app_mention_span("hi @app", 7) == (3, 7, "")
    assert active_app_mention_span("hi @app:", 8) == (3, 8, "")
    assert active_app_mention_span("hi @app:de", 10) == (3, 10, "de")
    assert active_app_mention_span("hi @mcp:foo", 11) is None

    new_text, new_cursor = apply_app_mention("hi @app:de", 10, "demo-ping")
    assert new_text == "hi @app:demo-ping "
    assert new_cursor == len(new_text)

    print("app mention ok")


if __name__ == "__main__":
    main()
