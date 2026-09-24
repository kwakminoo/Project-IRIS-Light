"""위키와 콘텐츠 가져오기 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import WikiHost

def register_wiki_actions(window: WikiHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        Path,
        _log,
        err_result,
        ok_result,
    )

    def wiki_list(_a: dict[str, Any]) -> dict[str, Any]:
        notes = [
            {"rel_path": n.rel_path, "title": n.title, "folder": n.folder, "source": n.source}
            for n in window._iris_wiki.list_notes()
        ]
        return ok_result("wiki.list_notes", {"notes": notes, "count": len(notes)})

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
        try:
            path, rel = window._iris_wiki.write_inbox_note(
                title,
                content,
                source_url=source_url,
                rel_path=rel_in,
            )
        except ValueError as exc:
            return err_result("wiki.write_user_note", str(exc))
        except OSError as exc:
            return err_result("wiki.write_user_note", str(exc))
        wiki_rel = f"user/{rel}"
        window._on_obsidian_icon()
        window._obsidian_page.reload_graph()
        window._left_sidebar.obsidian_detail.reload()
        if open_note:
            window._obsidian_page.show_note(wiki_rel)
        _log(window, "wiki.write_user_note", True)
        return ok_result(
            "wiki.write_user_note",
            {
                "rel_path": wiki_rel,
                "path": str(path),
                "title": title,
                "opened": open_note,
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
        from iris.knowledge.wiki_summarize import summarize_for_wiki

        source = str(args.get("source") or args.get("path") or args.get("url") or "").strip()
        title_in = str(args.get("title") or "").strip() or None
        rel_in = str(args.get("rel_path") or "").strip() or None
        open_note = bool(args.get("open", True))
        mode = str(args.get("mode") or "raw").strip().lower()
        if mode not in ("raw", "summarize"):
            mode = "raw"
        if not source:
            return err_result("wiki.import_content", "source required (file path or http(s) URL)")
        summarize_fn = None
        if mode == "summarize":
            model = str(
                args.get("model")
                or window._chat.current_model()
                or getattr(window, "_saved_model", "")
                or window._settings.ollama_model
                or ""
            ).strip()
            if not model:
                return err_result("wiki.import_content", "model required for summarize mode")
            base = (window._settings.ollama_base_url or "http://127.0.0.1:11434/v1").strip()

            def _sum(text: str) -> str:
                return summarize_for_wiki(text, model=model, ollama_base_url=base)

            summarize_fn = _sum
        try:
            result = import_to_wiki(
                window._iris_wiki,
                source=source,
                title=title_in,
                mode=mode,
                rel_path=rel_in,
                summarize_fn=summarize_fn,
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
        window._on_obsidian_icon()
        window._obsidian_page.reload_graph()
        window._left_sidebar.obsidian_detail.reload()
        if open_note:
            window._obsidian_page.show_note(wiki_rel)
        _log(window, "wiki.import_content", True)
        result = {**result, "opened": open_note}
        return ok_result("wiki.import_content", result)

    reg.register("wiki.list_notes", wiki_list, summary="List Iris Wiki note paths")

    reg.register(
        "wiki.open_note",
        wiki_open,
        summary="Open Iris Wiki workspace and show note by rel_path",
    )

    reg.register("wiki.reload", wiki_reload, summary="Reload Iris Wiki graph/detail")

    reg.register(
        "wiki.write_user_note",
        wiki_write,
        summary="Save markdown to Iris Wiki user/ (default inbox/{slug}.md) and show it",
        risk="medium",
    )

    reg.register(
        "content.extract",
        content_extract,
        summary="Extract text from PDF, text file, or http(s) URL",
        risk="low",
    )

    reg.register(
        "wiki.import_content",
        wiki_import_content,
        summary="Extract PDF/URL/file text and save to Iris Wiki inbox, then open in UI (mode=raw|summarize)",
        risk="medium",
    )
