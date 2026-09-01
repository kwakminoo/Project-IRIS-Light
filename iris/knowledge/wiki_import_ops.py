"""위키 import 공통 로직 (로컬·control surface)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from iris.knowledge.content_extract import extract_from_source
from iris.knowledge.iris_wiki import IrisWiki, slugify_note_name


def _unique_inbox_rel(wiki: IrisWiki, title: str) -> str:
    base = slugify_note_name(title)
    rel = f"inbox/{base}.md"
    path = wiki.user_root / rel
    if not path.is_file():
        return rel
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"inbox/{base}-{stamp}.md"


def prepare_wiki_body(
    source: str,
    *,
    mode: str = "raw",
    summarize_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    data = extract_from_source(source)
    body = str(data["text"]).strip()
    if not body:
        raise ValueError("no content extracted")
    if mode == "summarize":
        if summarize_fn is None:
            raise ValueError("summarize_fn required for summarize mode")
        body = summarize_fn(body).strip() or body
    title = str(data["title"])
    source_url = source if str(data["kind"]) == "url" else str(data["source"])
    return {
        "title": title,
        "body": body,
        "source_url": source_url,
        "kind": data["kind"],
        "source": data["source"],
        "truncated": bool(data["truncated"]),
    }


def import_to_wiki(
    wiki: IrisWiki,
    *,
    source: str,
    title: str | None = None,
    mode: str = "raw",
    rel_path: str | None = None,
    open_note: bool = True,
    summarize_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    prepared = prepare_wiki_body(source, mode=mode, summarize_fn=summarize_fn)
    note_title = (title or prepared["title"] or "untitled").strip()
    rel_in = rel_path
    if not rel_in:
        rel_in = _unique_inbox_rel(wiki, note_title)
    path, rel = wiki.write_inbox_note(
        note_title,
        prepared["body"],
        source_url=prepared["source_url"],
        rel_path=rel_in,
    )
    wiki_rel = f"user/{rel}"
    return {
        "rel_path": wiki_rel,
        "path": str(path),
        "title": note_title,
        "kind": prepared["kind"],
        "source": prepared["source"],
        "truncated": prepared["truncated"],
        "chars": len(prepared["body"]),
        "mode": mode,
        "opened": open_note,
    }
