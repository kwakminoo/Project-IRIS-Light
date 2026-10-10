"""저장 요청을 분류된 경로에 쓴다. 분류기를 안 넘기면 예전처럼 inbox."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from iris.knowledge.history_index import Embedder
from iris.knowledge.iris_wiki import IrisWiki, slugify_note_name
from iris.knowledge.wiki_classify import CLASSIFY_SYSTEM, Namer, classify_note
from iris.knowledge.wiki_note_index import index_rel
from iris.knowledge.wiki_places import project_slug as slug_from_root
from iris.storage.database import Database


def unique_rel(wiki: IrisWiki, folder: str, title: str) -> str:
    folder = (folder or "").strip("/")
    name = Path(str(title).replace("\\", "/")).name
    if Path(name).suffix:
        name = Path(name).stem or name
    base = slugify_note_name(name or title)
    rel = f"{folder}/{base}.md" if folder else f"{base}.md"
    if not (wiki.user_root / rel).is_file():
        return rel
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = f"{folder}/{base}-{stamp}.md" if folder else f"{base}-{stamp}.md"
    counter = 2
    while (wiki.user_root / candidate).is_file():
        extra = f"-{counter}"
        candidate = (
            f"{folder}/{base}-{stamp}{extra}.md" if folder else f"{base}-{stamp}{extra}.md"
        )
        counter += 1
    return candidate


def _explicit_rel(rel_path: str | None, *, classify: bool) -> str:
    """분류 중에는 inbox 경로를 예전 기본값으로 보고 다시 정한다."""
    rel = (rel_path or "").strip().lstrip("/").replace("\\", "/")
    if rel.startswith("user/"):
        rel = rel[len("user/") :]
    if not rel:
        return ""
    if classify and (rel.startswith("inbox/") or rel == "inbox"):
        return ""
    return rel


def file_user_note(
    wiki: IrisWiki,
    title: str,
    body: str,
    *,
    source_url: str = "",
    rel_path: str | None = None,
    db: Database | None = None,
    embedder: Embedder | None = None,
    namer: Namer | None = None,
    opened_slug: str = "",
    classify: bool = False,
) -> dict[str, Any]:
    """노트를 쓰고, db 가 있으면 색인한다."""
    title = (title or "").strip() or "untitled"
    text = (body or "").strip()
    if not text:
        raise ValueError("content required")
    explicit = _explicit_rel(rel_path, classify=classify)
    ask = False
    place = ""
    if explicit:
        rel = explicit if explicit.endswith(".md") else f"{explicit}.md"
        place = rel.rsplit("/", 1)[0] if "/" in rel else ""
    elif classify:
        decision = classify_note(
            title,
            text,
            db=db,
            embedder=embedder,
            namer=namer,
            project_slug=opened_slug,
        )
        ask = decision.ask_folder
        place = decision.folder or "inbox"
        rel = unique_rel(wiki, decision.folder or "inbox", title)
    else:
        rel = unique_rel(wiki, "inbox", title)
        place = "inbox"
    path, written = wiki.write_inbox_note(
        title, text, source_url=source_url, rel_path=rel,
    )
    if db is not None:
        try:
            index_rel(db, wiki, written, embedder=embedder, place_id=place)
        except OSError:
            pass
    return {
        "path": str(path),
        "rel_path": f"user/{written}",
        "title": title,
        "ask_folder": ask,
        "place": place,
    }


def open_classifier(base_url: str, history_settings, model: str, *, db=None, settings=None):
    """임베더와 JSON 분류 호출. 실패하면 None. 키워드 대체는 없다."""
    embedder = None
    namer = None
    base = (base_url or "http://127.0.0.1:11434/v1").strip()
    try:
        from iris.infrastructure.ollama_client import OllamaClient
        from iris.runtime.model_switch import resolve_embedder

        probe = OllamaClient(base, timeout_sec=4.0)
        embedder = resolve_embedder(history_settings, probe)
    except Exception:
        embedder = None
    model_name = (model or "").strip()
    if not model_name:
        return embedder, None
    from iris.runtime.backend_route import ask_selected_model, settings_for_model

    bound = settings_for_model(settings, base)

    def namer(prompt: str, _model=model_name, _settings=bound, _db=db) -> str:
        return ask_selected_model(
            _settings, _db, _model, prompt, system=CLASSIFY_SYSTEM, timeout_sec=45.0,
        )

    return embedder, namer


def filing_kwargs(
    *, db, base_url: str, history_settings, model: str, project_root: str, settings=None,
) -> dict:
    embedder, namer = open_classifier(
        base_url, history_settings, model, db=db, settings=settings,
    )
    return {
        "db": db,
        "embedder": embedder,
        "namer": namer,
        "opened_slug": slug_from_root(project_root),
        "classify": True,
    }
