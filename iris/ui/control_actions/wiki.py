"""위키와 콘텐츠 가져오기 컨트롤 액션."""

from __future__ import annotations

from typing import Any, Callable
from urllib.request import Request, urlopen

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import WikiHost

_PAGE_CAP = 80
_LIST_CAP = 40


def page_note_rows(notes: list, cap: int = _LIST_CAP) -> dict[str, Any]:
    """한 페이지와 전체 개수. 잘리면 truncated 가 참이다."""
    total = len(notes)
    page = list(notes[:cap])
    return {
        "notes": page,
        "count": len(page),
        "total": total,
        "truncated": total > len(page),
    }


def _page_limit(raw: object) -> int:
    try:
        n = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _PAGE_CAP
    if n < 1:
        return _PAGE_CAP
    return min(n, _PAGE_CAP)


def _truthy(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _dedupe_sources(items: list[str]) -> list[str]:
    from urllib.parse import urldefrag

    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = item.strip()
        if not text:
            continue
        key = text
        if text.lower().startswith(("http://", "https://")):
            key = urldefrag(text)[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _move_sources(args: dict[str, Any]) -> list[str]:
    raw = args.get("sources")
    if raw is None:
        raw = args.get("from") or args.get("from_folder") or args.get("rel_path") or args.get("path")
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    return [text] if text else []


def _page_sources(args: dict[str, Any]) -> list[str]:
    raw = args.get("sources")
    items: list[str] = []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw if str(x).strip()]
    elif isinstance(raw, str) and raw.strip():
        items = [raw.strip()]
    if items:
        return _dedupe_sources(items)
    one = str(args.get("source") or args.get("path") or args.get("url") or "").strip()
    return [one] if one else []


def _fetch_html(url: str) -> tuple[str, str]:
    req = Request(url, headers={"User-Agent": "Iris-Wiki/1.0 (+local content import)"})
    with urlopen(req, timeout=20) as resp:
        final = resp.geturl()
        raw = resp.read(2_000_000)
        ctype = (resp.headers.get("Content-Type") or "").lower()
    charset = "utf-8"
    marker = "charset="
    if marker in ctype:
        charset = ctype.split(marker, 1)[1].split(";", 1)[0].strip(" \"'")
    return final, raw.decode(charset, errors="replace")


def _merge_discovered(
    sources: list[str],
    args: dict[str, Any],
    limit: int,
    fetch_html: Callable[[str], tuple[str, str]],
) -> tuple[list[str], bool]:
    from iris.knowledge.wiki_import_ops import collect_same_origin_links

    merged = list(sources)
    if _truthy(args.get("discover")):
        root = next(
            (item for item in sources if item.lower().startswith(("http://", "https://"))),
            "",
        )
        if root:
            try:
                final, html = fetch_html(root)
            except (OSError, TimeoutError, ValueError):
                final, html = "", ""
            if html:
                extra = collect_same_origin_links(final or root, html, limit=limit)
                merged = _dedupe_sources([*sources, *extra])
    return merged[:limit], len(merged) > limit

def _wiki_filing(window: WikiHost) -> dict:
    from iris.knowledge.wiki_filing import filing_kwargs

    model = str(
        window._chat.current_model()
        or getattr(window, "_saved_model", "")
        or window._settings.ollama_model
        or ""
    ).strip()
    root = ""
    getter = getattr(window, "_current_project_root", None)
    if callable(getter):
        try:
            root = str(getter() or "")
        except Exception:
            root = ""
    return filing_kwargs(
        db=window._db,
        base_url=window._settings.ollama_base_url,
        history_settings=window._model_switch.history_settings,
        model=model,
        project_root=root,
        settings=window._settings,
    )


def register_wiki_actions(window: WikiHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        Path,
        _call_on_ui,
        _log,
        err_result,
        ok_result,
    )

    def _model_name(args: dict[str, Any]) -> str:
        return str(
            args.get("model")
            or window._chat.current_model()
            or getattr(window, "_saved_model", "")
            or window._settings.ollama_model
            or ""
        ).strip()

    def _summary_and_vision(args: dict[str, Any]):
        from iris.knowledge.page_vision import transcribe_images
        from iris.knowledge.wiki_summarize import summarize_for_wiki

        model = _model_name(args)
        if not model:
            return None, None
        base = (window._settings.ollama_base_url or "http://127.0.0.1:11434/v1").strip()

        def _sum(text: str) -> str:
            return summarize_for_wiki(
                text,
                model=model,
                ollama_base_url=base,
                settings=window._settings,
                db=window._db,
            )

        spec = {
            "model": model,
            "ollama_base_url": base,
            "api_base_url": "",
            "api_key": "",
            "auth_style": "bearer",
        }
        getter = getattr(window, "_material_vision_spec", None)
        if callable(getter):
            try:
                spec = dict(getter(model))
            except Exception:
                pass

        def _vision(pngs: list[bytes]) -> str:
            return transcribe_images(
                pngs,
                model=str(spec.get("model") or model),
                ollama_base_url=str(spec.get("ollama_base_url") or base),
                api_base_url=str(spec.get("api_base_url") or ""),
                api_key=str(spec.get("api_key") or ""),
                auth_style=str(spec.get("auth_style") or "bearer"),
            )

        return _sum, _vision

    def _show_saved(rel: str, *, open_note: bool) -> None:
        def _do() -> None:
            window._on_obsidian_icon()
            window._obsidian_page.reload_graph()
            window._left_sidebar.obsidian_detail.reload()
            if open_note and rel:
                window._obsidian_page.show_note(rel)

        _call_on_ui(window, _do)

    def wiki_list(_a: dict[str, Any]) -> dict[str, Any]:
        notes = [
            {"rel_path": n.rel_path, "title": n.title, "folder": n.folder, "source": n.source}
            for n in window._iris_wiki.list_notes()
        ]
        page = page_note_rows(notes)
        window._wiki_list_truncated = bool(page["truncated"])
        window._wiki_list_total = int(page["total"])
        return ok_result("wiki.list_notes", page)

    def wiki_open(args: dict[str, Any]) -> dict[str, Any]:
        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        if not rel:
            return err_result("wiki.open_note", "rel_path required")
        window._on_obsidian_icon()
        window._obsidian_page.show_note(rel)
        window._left_sidebar.obsidian_detail.reload()
        _log(window, "wiki.open_note", True)
        return ok_result("wiki.open_note", {"rel_path": rel})

    def wiki_reload(_a: dict[str, Any]) -> dict[str, Any]:
        if window._workspace_mode != "obsidian":
            window._on_obsidian_icon()
        else:
            window._left_sidebar.obsidian_detail.reload()
            window._obsidian_page.reload_graph()
        _log(window, "wiki.reload", True)
        return ok_result("wiki.reload", {})

    def wiki_write(args: dict[str, Any]) -> dict[str, Any]:
        title = str(args.get("title") or "").strip()
        content = str(args.get("content") or args.get("body") or "").strip()
        source_url = str(args.get("source_url") or args.get("url") or "").strip()
        rel_in = str(args.get("rel_path") or args.get("path") or "").strip() or None
        open_note = bool(args.get("open", True))
        if not title and rel_in:
            stem = Path(rel_in.replace("\\", "/")).stem
            title = stem or "untitled"
        if not title:
            return err_result("wiki.write_user_note", "title required")
        if not content:
            return err_result("wiki.write_user_note", "content required")
        from iris.knowledge.wiki_filing import file_user_note
        from iris.knowledge.wiki_original import compose_wiki_body, insert_original_marker, store_original

        summarize_fn, _vision = _summary_and_vision(args)
        if not content.lstrip().startswith("## 전체 요약"):
            summary = summarize_fn(content).strip() if summarize_fn else ""
            content = compose_wiki_body(summary=summary, original=content)
        try:
            filed = file_user_note(
                window._iris_wiki,
                title,
                content,
                source_url=source_url,
                rel_path=rel_in,
                **_wiki_filing(window),
            )
        except ValueError as exc:
            return err_result("wiki.write_user_note", str(exc))
        except OSError as exc:
            return err_result("wiki.write_user_note", str(exc))
        kind = ""
        low = source_url.lower()
        if low.startswith(("http://", "https://")):
            kind = "url"
        elif low.endswith(".pdf"):
            kind = "pdf"
        if kind:
            asset = store_original(Path(str(filed["path"])), kind=kind, source=source_url)
            if asset:
                insert_original_marker(Path(str(filed["path"])), asset)
        wiki_rel = str(filed["rel_path"])
        _show_saved(wiki_rel, open_note=open_note)
        _log(window, "wiki.write_user_note", True)
        return ok_result(
            "wiki.write_user_note",
            {
                "rel_path": wiki_rel,
                "path": str(filed["path"]),
                "title": title,
                "opened": open_note,
                "place": filed.get("place") or "",
                "ask_folder": bool(filed.get("ask_folder")),
            },
        )

    def content_extract(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.content_extract import (
            UnsupportedAttachmentTypeError,
            extract_from_source,
        )

        source = str(args.get("source") or args.get("path") or args.get("url") or "").strip()
        if not source:
            return err_result("content.extract", "source required (file path or http(s) URL)")
        try:
            data = extract_from_source(source)
        except UnsupportedAttachmentTypeError as exc:
            return err_result(
                "content.extract",
                str(exc),
                {
                    "error_code": exc.code,
                    "help_url": "https://iris-light-site.vercel.app/#install",
                    "scope": "attachment_extract",
                },
            )
        except (ValueError, OSError, RuntimeError) as exc:
            return err_result("content.extract", str(exc))
        _log(window, "content.extract", True)
        return ok_result(
            "content.extract",
            {
                "kind": data["kind"],
                "title": data["title"],
                "text": data["text"],
                "source": data["source"],
                "truncated": data["truncated"],
                "chars": len(str(data["text"])),
            },
        )

    def wiki_import_content(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.content_extract import UnsupportedAttachmentTypeError
        from iris.knowledge.wiki_import_ops import import_to_wiki

        source = str(args.get("source") or args.get("path") or args.get("url") or "").strip()
        title_in = str(args.get("title") or "").strip() or None
        rel_in = str(args.get("rel_path") or "").strip() or None
        open_note = bool(args.get("open", True))
        mode = str(args.get("mode") or "raw").strip().lower()
        if mode not in ("raw", "summarize"):
            mode = "raw"
        if not source:
            return err_result("wiki.import_content", "source required (file path or http(s) URL)")
        summarize_fn, vision = _summary_and_vision(args)
        try:
            result = import_to_wiki(
                window._iris_wiki,
                source=source,
                title=title_in,
                mode=mode,
                rel_path=rel_in,
                summarize_fn=summarize_fn,
                vision_reader=vision,
                **_wiki_filing(window),
            )
        except UnsupportedAttachmentTypeError as exc:
            return err_result(
                "wiki.import_content",
                str(exc),
                {
                    "error_code": exc.code,
                    "help_url": "https://iris-light-site.vercel.app/#install",
                    "scope": "attachment_extract",
                },
            )
        except (ValueError, OSError, RuntimeError) as exc:
            return err_result("wiki.import_content", str(exc))
        wiki_rel = str(result["rel_path"])
        _show_saved(wiki_rel, open_note=open_note)
        _log(window, "wiki.import_content", True)
        result = {**result, "opened": open_note}
        return ok_result("wiki.import_content", result)

    def wiki_import_pages(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.wiki_import_ops import import_pages

        sources = _page_sources(args)
        if not sources:
            return err_result("wiki.import_pages", "sources or source required")
        mode = str(args.get("mode") or "raw").strip().lower()
        if mode not in ("raw", "summarize"):
            mode = "raw"
        summarize_fn, vision = _summary_and_vision(args)
        limit = _page_limit(args.get("limit"))
        merged, truncated = _merge_discovered(sources, args, limit, _fetch_html)
        data = import_pages(
            window._iris_wiki,
            merged,
            mode=mode,
            summarize_fn=summarize_fn,
            vision_reader=vision,
            **_wiki_filing(window),
        )
        data["truncated"] = truncated
        last = next(
            (str(item["rel_path"]) for item in reversed(data["items"]) if item.get("ok")),
            "",
        )
        if data["saved"] and last:
            _show_saved(last, open_note=True)
        _log(
            window,
            f"wiki.import_pages saved={data['saved']} failed={data['failed']}",
            True,
        )
        return ok_result("wiki.import_pages", data)

    def wiki_search(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.code_note_prompt import search_code_notes
        from iris.knowledge.wiki_filing import open_classifier
        from iris.knowledge.wiki_note_index import search_notes, sync_knowledge_notes

        query = str(args.get("query") or args.get("q") or "").strip()
        if not query:
            return err_result("wiki.search", "query required")
        try:
            limit = int(args.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = min(8, max(1, limit))
        model = str(
            window._chat.current_model()
            or getattr(window, "_saved_model", "")
            or window._settings.ollama_model
            or ""
        ).strip()
        embedder, _namer = open_classifier(
            window._settings.ollama_base_url,
            window._model_switch.history_settings,
            model,
        )
        try:
            sync_knowledge_notes(window._db, window._iris_wiki)
            hits = search_notes(window._db, query, embedder=embedder, limit=limit)
            code_hits = search_code_notes(window._iris_wiki._docs.root, query, limit=limit)
        except OSError as exc:
            return err_result("wiki.search", str(exc))
        _log(window, "wiki.search", True)
        return ok_result(
            "wiki.search",
            {
                "hits": [
                    {
                        "rel_path": f"user/{hit.rel_path}",
                        "title": hit.title,
                        "excerpt": hit.excerpt,
                        "score": hit.score,
                        "similarity": hit.similarity,
                        "source": "wiki-note",
                    }
                    for hit in hits
                ],
                "code_hits": [
                    {
                        "rel_path": f"docs/{hit.rel_path}",
                        "title": hit.title,
                        "excerpt": hit.excerpt,
                        "score": hit.score,
                        "source": "code-note",
                    }
                    for hit in code_hits
                ],
                "count": len(hits),
            },
        )

    def wiki_read(args: dict[str, Any]) -> dict[str, Any]:
        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        if not rel:
            return err_result("wiki.read_note", "rel_path required")
        try:
            text = window._iris_wiki.read_note(rel)
        except (OSError, ValueError) as exc:
            return err_result("wiki.read_note", str(exc))
        capped = text[:20_000]
        _log(window, "wiki.read_note", True)
        return ok_result(
            "wiki.read_note",
            {
                "rel_path": rel,
                "text": capped,
                "chars": len(text),
                "truncated": len(text) > len(capped),
            },
        )

    def wiki_delete(args: dict[str, Any]) -> dict[str, Any]:
        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        if not rel:
            return err_result("wiki.delete_note", "rel_path required")
        if not rel.replace("\\", "/").startswith("user/"):
            return err_result("wiki.delete_note", "user notes only")
        try:
            path = window._iris_wiki.delete_user_note(rel)
        except (OSError, ValueError) as exc:
            return err_result("wiki.delete_note", str(exc))
        window._on_obsidian_icon()
        window._obsidian_page.reload_graph()
        window._left_sidebar.obsidian_detail.reload()
        _log(window, "wiki.delete_note", True)
        return ok_result("wiki.delete_note", {"rel_path": rel, "path": str(path)})

    def wiki_move(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.wiki_move import move_user_bytes

        sources = _move_sources(args)
        dest = str(args.get("dest_folder") or args.get("folder") or "").strip()
        if not sources:
            return err_result("wiki.move_notes", "sources required")
        if not dest:
            return err_result("wiki.move_notes", "dest_folder required")
        try:
            moved = move_user_bytes(window._iris_wiki, sources, dest)
        except (OSError, ValueError) as exc:
            return err_result("wiki.move_notes", str(exc))
        complete = int(moved.get("count") or 0) > 0 and not moved.get("left")
        window._wiki_turn_moved = complete
        window._wiki_turn_moved_folder = complete and bool(moved.get("folders"))
        if complete:
            window._wiki_turn_wrote = True
            window._wiki_turn_changed = True
        db = getattr(window, "_db", None)
        if db is not None:
            try:
                from iris.knowledge.wiki_note_index import sync_knowledge_notes

                sync_knowledge_notes(db, window._iris_wiki)
            except Exception as exc:  # noqa: BLE001 — 디스크 이동은 유지한다
                moved["index_error"] = str(exc)
        window._on_obsidian_icon()
        window._obsidian_page.reload_graph()
        window._left_sidebar.obsidian_detail.reload()
        if not complete:
            left = ", ".join(str(item) for item in (moved.get("left") or []))
            return err_result("wiki.move_notes", f"sources still present: {left}")
        _log(window, "wiki.move_notes", True)
        return ok_result("wiki.move_notes", moved)

    def wiki_reprocess(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.wiki_command import WikiCommand
        from iris.knowledge.wiki_ops import execute_wiki_command
        from iris.knowledge.wiki_summarize import summarize_for_wiki, translate_for_wiki
        from iris.ui.control_bindings import _call_on_ui

        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        if not rel:
            return err_result("wiki.reprocess_note", "rel_path required")
        model = _model_name(args)
        if not model:
            return err_result("wiki.reprocess_note", "model required")
        base = (window._settings.ollama_base_url or "http://127.0.0.1:11434/v1").strip()
        summarize = _truthy(args.get("summarize", True))
        translate = _truthy(args.get("translate", True))

        def _sum(text: str) -> str:
            return summarize_for_wiki(
                text, model=model, ollama_base_url=base,
                settings=window._settings, db=window._db,
            )

        def _tr(text: str) -> str:
            return translate_for_wiki(
                text, model=model, ollama_base_url=base,
                settings=window._settings, db=window._db,
            )

        from iris.knowledge.wiki_filing import filing_kwargs
        from iris.storage.failover_prefs import load_history_settings

        try:
            filing = filing_kwargs(
                db=window._db,
                base_url=base,
                history_settings=load_history_settings(window._db),
                model=model,
                project_root="",
                settings=window._settings,
            )
            result = execute_wiki_command(
                window._iris_wiki,
                WikiCommand(
                    op="reprocess",
                    rel_path=rel,
                    keep_original=True,
                    summarize=summarize,
                    translate=translate,
                ),
                summarize_fn=_sum if summarize else None,
                translate_fn=_tr if translate else None,
                filing=filing,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            return err_result("wiki.reprocess_note", str(exc))
        wiki_rel = str(result.get("rel_path") or rel)

        def _show() -> None:
            window._on_obsidian_icon()
            window._obsidian_page.reload_graph()
            window._left_sidebar.obsidian_detail.reload()
            window._obsidian_page.show_note(wiki_rel)

        _call_on_ui(window, _show)
        _log(window, "wiki.reprocess_note", True)
        return ok_result("wiki.reprocess_note", result)

    reg.register(
        "wiki.list_notes",
        wiki_list,
        summary="List Iris Wiki note paths. count is this page, total is the vault, truncated is true when total is larger.",
    )

    reg.register(
        "wiki.read_note",
        wiki_read,
        summary="Read one Iris Wiki note body by rel_path",
    )

    reg.register(
        "wiki.delete_note",
        wiki_delete,
        summary="Delete one user Iris Wiki note by rel_path",
        risk="medium",
    )

    reg.register(
        "wiki.move_notes",
        wiki_move,
        summary="Copy existing user notes to dest_folder as the same bytes, then delete the sources. sources: file or folder rel_paths. Folder sources keep their folder name under dest_folder.",
        risk="medium",
    )

    reg.register(
        "wiki.reprocess_note",
        wiki_reprocess,
        summary="Keep the note, write a Korean summary on top, and Korean under each paragraph. One call. Do not paste the note into write_user_note.",
        risk="medium",
    )

    reg.register(
        "wiki.open_note",
        wiki_open,
        summary="Open Iris Wiki workspace and show note by rel_path",
    )

    reg.register("wiki.reload", wiki_reload, summary="Reload Iris Wiki graph/detail")

    reg.register(
        "wiki.search",
        wiki_search,
        summary="Search saved Iris Wiki notes (FTS and embeddings). Excerpts only. Not conversation history.",
    )

    reg.register(
        "wiki.write_user_note",
        wiki_write,
        summary="Save markdown into a classified Iris Wiki folder (사용자, 학습자료, 인사이트, projects, research). Ambiguous notes stay in inbox. Do not use this to move existing notes; wiki.move_notes copies bytes and deletes the source.",
        risk="medium",
    )

    reg.register(
        "content.extract",
        content_extract,
        summary="Extract text from PDF (scanned image pages included), Office, text, image, or http(s) URL. Chat already attaches [자료 본문] before the answer.",
        risk="low",
    )

    reg.register(
        "wiki.import_content",
        wiki_import_content,
        summary="Save PDF/URL/file into Iris Wiki with a full summary and key concepts on top, and the original below. PDF is copied; web is one HTML file. No text cap. Image pages are read one by one.",
        risk="medium",
    )

    reg.register(
        "wiki.import_pages",
        wiki_import_pages,
        summary="Save many pages into classified Iris Wiki folders in one call (sources or source, discover=true, limit<=80). Do not loop import_content per page.",
        risk="medium",
    )
