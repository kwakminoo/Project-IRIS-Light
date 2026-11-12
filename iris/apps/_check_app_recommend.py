"""App recommendations from composer context (lexical overlap).

Run: .venv\\Scripts\\python.exe -m iris.apps._check_app_recommend
"""

from __future__ import annotations

from iris.apps.directory import BUILTIN_APPS, AppDirectoryEntry
from iris.apps.recommend import RecommendQuery, recommend_apps


def _entries() -> list[AppDirectoryEntry]:
    extra = AppDirectoryEntry(
        id="other-note",
        title="Note Pad",
        summary="Plain notes",
        resource_uri="note.html",
        source="installed",
    )
    return list(BUILTIN_APPS) + [extra]


def main() -> None:
    rows = _entries()

    ping = recommend_apps("try ping please", rows)
    assert ping and ping[0].id == "demo-ping", [e.id for e in ping]

    demo = recommend_apps("데모 열어줘", rows)
    assert demo and demo[0].id == "demo-ping", [e.id for e in demo]

    empty = recommend_apps("", rows)
    assert empty == [], empty

    whitespace = recommend_apps("   \n\t  ", rows)
    assert whitespace == [], whitespace

    no_hit = recommend_apps("calendar invite tomorrow", rows)
    assert no_hit == [], no_hit

    query = RecommendQuery(context="ping")
    from_query = recommend_apps(query.context, rows)
    assert from_query and from_query[0].id == "demo-ping"

    print("app recommend ok")


if __name__ == "__main__":
    main()
