"""위키 명령을 파일에 실행한다. 모델은 요약·문단 번역에만 쓴다."""

from __future__ import annotations

import re
from typing import Any, Callable

from iris.knowledge.iris_wiki import IrisWiki, markdown_heading
from iris.knowledge.wiki_command import WikiCommand
from iris.knowledge.wiki_import_ops import import_to_wiki, save_answer_to_wiki

# ponytail: 문단당 번역 1회, 24회에서 멈춘다. 나머지는 원문만 남긴다.
# 로컬 번역기로 바꿀 때는 이 상한과 translate_fn 호출만 바꾸면 된다.
_MAX_TRANSLATE_CALLS = 24
SummarizeFn = Callable[[str], str]
TranslateFn = Callable[[str], str]


def split_paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", text or "") if part.strip()]
    if parts:
        return parts
    one = (text or "").strip()
    return [one] if one else []


def article_from_note(markdown: str) -> tuple[str, str, str]:
    """제목, 출처, 재가공에 쓸 원문. 기존 번역 인용은 원문에서 뺀다."""
    title = ""
    source = ""
    kept: list[str] = []
    for index, line in enumerate((markdown or "").splitlines()):
        stripped = line.strip()
        if index < 8 and stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
            continue
        if stripped.lower().startswith("- source:"):
            source = stripped.split(":", 1)[1].strip()
            continue
        if stripped.lower().startswith("> updated:"):
            continue
        kept.append(line)
    body = "\n".join(kept).strip()
    if "## 원본" in body:
        original = body.split("## 원본", 1)[1]
        paragraphs: list[str] = []
        for block in re.split(r"\n\s*\n", original):
            lines = [
                line
                for line in block.splitlines()
                if not line.strip().lower().startswith("> ko:")
                and not line.strip().lower().startswith("- iris-original:")
            ]
            text = "\n".join(lines).strip()
            if text and not text.startswith("## "):
                paragraphs.append(text)
        body = "\n\n".join(paragraphs).strip()
    elif "## 원문" in body:
        original = body.split("## 원문", 1)[1]
        paragraphs: list[str] = []
        for block in re.split(r"\n\s*\n", original):
            lines = [
                line
                for line in block.splitlines()
                if not line.strip().lower().startswith("> ko:")
            ]
            text = "\n".join(lines).strip()
            if text and not text.startswith("## "):
                paragraphs.append(text)
        body = "\n\n".join(paragraphs).strip()
    if not title:
        title = markdown_heading(markdown)
    return title, source, body


def compose_reprocessed(
    *,
    summary: str,
    paragraphs: list[str],
    translations: list[str],
) -> str:
    lines: list[str] = []
    if (summary or "").strip():
        lines.extend(["## 정리", "", summary.strip(), ""])
    lines.extend(["## 원문", ""])
    for index, paragraph in enumerate(paragraphs):
        lines.append(paragraph.strip())
        lines.append("")
        ko = translations[index].strip() if index < len(translations) else ""
        if ko:
            lines.append(f"> ko: {ko}")
            lines.append("")
    return "\n".join(lines).strip()


def translate_paragraphs(paragraphs: list[str], translate_fn: TranslateFn) -> list[str]:
    out: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        if index >= _MAX_TRANSLATE_CALLS:
            out.append("")
            continue
        out.append((translate_fn(paragraph) or "").strip())
    return out


def _resolve(wiki: IrisWiki, command: WikiCommand) -> str:
    rel = (command.rel_path or "").replace("\\", "/").strip()
    if rel:
        return rel
    hint = (command.title or "").strip()
    if not hint:
        raise ValueError("어느 노트인지 알 수 없습니다. 경로를 알려 주세요.")
    from iris.knowledge.iris_wiki import match_wiki_notes

    hits = [
        note
        for note in match_wiki_notes(wiki.list_notes(), hint, limit=5)
        if note.rel_path.startswith("user/")
    ]
    if len(hits) == 1:
        return hits[0].rel_path
    if len(hits) > 1:
        raise ValueError("노트가 여러 개입니다. 경로를 알려 주세요.")
    raise ValueError("어느 노트인지 알 수 없습니다. 경로를 알려 주세요.")


def _result(
    *,
    op: str,
    rel_path: str = "",
    path: str = "",
    title: str = "",
    wrote: bool = False,
    opened: bool = False,
    changed: bool = False,
    mode: str = "",
    message: str = "",
    body: str = "",
) -> dict[str, Any]:
    return {
        "op": op,
        "rel_path": rel_path,
        "path": path,
        "title": title,
        "wrote": wrote,
        "opened": opened,
        "changed": changed,
        "mode": mode,
        "message": message,
        "body": body,
    }


def _reprocess_body(
    body: str,
    *,
    summarize: bool,
    translate: bool,
    summarize_fn: SummarizeFn | None,
    translate_fn: TranslateFn | None,
) -> str:
    paragraphs = split_paragraphs(body)
    summary = ""
    if summarize:
        if summarize_fn is None:
            raise RuntimeError("요약에는 모델 선택이 필요합니다.")
        summary = summarize_fn(body).strip()
    translations = [""] * len(paragraphs)
    if translate:
        if translate_fn is None:
            raise RuntimeError("문단 번역에는 모델 선택이 필요합니다.")
        translations = translate_paragraphs(paragraphs, translate_fn)
    if not summary and not any(translations):
        raise RuntimeError("정리 결과가 비어 있습니다.")
    return compose_reprocessed(
        summary=summary,
        paragraphs=paragraphs,
        translations=translations,
    )


def execute_wiki_command(
    wiki: IrisWiki,
    command: WikiCommand,
    *,
    summarize_fn: SummarizeFn | None = None,
    translate_fn: TranslateFn | None = None,
    vision_reader=None,
    filing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    filing = dict(filing or {})
    op = command.op

    if op == "list":
        notes = wiki.list_notes()
        lines = [f"- {note.title} (`{note.rel_path}`)" for note in notes[:30]]
        message = "\n".join(lines) if lines else "노트가 없습니다."
        return _result(op="list", message=message)

    if op == "save" and command.content and not command.needs_model():
        filed = save_answer_to_wiki(
            wiki,
            title=command.title or "검색 결과",
            content=command.content,
            summarize_fn=summarize_fn,
            **filing,
        )
        return _result(
            op="save",
            rel_path=str(filed.get("rel_path") or ""),
            path=str(filed.get("path") or ""),
            title=str(filed.get("title") or command.title),
            wrote=True,
            changed=True,
            opened=True,
            mode="raw",
            body=command.content,
        )

    if op == "save" and command.source:
        filed = import_to_wiki(
            wiki,
            source=command.source,
            title=command.title or None,
            mode="summarize" if summarize_fn else "raw",
            summarize_fn=summarize_fn,
            vision_reader=vision_reader,
            **filing,
        )
        return _result(
            op="save",
            rel_path=str(filed.get("rel_path") or ""),
            path=str(filed.get("path") or ""),
            title=str(filed.get("title") or ""),
            wrote=True,
            changed=True,
            opened=True,
            mode="summarize" if summarize_fn else "raw",
        )

    if op == "reprocess":
        from iris.knowledge.wiki_filing import file_user_note

        rel = _resolve(wiki, command)
        original = article_from_note(wiki.read_note(rel))
        title, source, article = original
        if not article.strip():
            raise ValueError("노트 본문이 비어 있습니다.")
        body = _reprocess_body(
            article,
            summarize=command.summarize,
            translate=command.translate,
            summarize_fn=summarize_fn,
            translate_fn=translate_fn,
        )
        filed = file_user_note(
            wiki,
            title or "untitled",
            body,
            source_url=source,
            rel_path=rel,
            **{k: v for k, v in filing.items() if k != "classify"},
            classify=False,
        )
        return _result(
            op="reprocess",
            rel_path=str(filed.get("rel_path") or rel),
            path=str(filed.get("path") or ""),
            title=title,
            wrote=True,
            changed=True,
            opened=True,
            mode="reprocess",
            body=body,
        )

    if op == "open":
        rel = _resolve(wiki, command)
        wiki.read_note(rel)
        return _result(op="open", rel_path=rel, opened=True, message="open")

    if op == "delete":
        rel = _resolve(wiki, command)
        if not rel.startswith("user/"):
            raise ValueError("사용자 노트만 삭제할 수 있습니다.")
        path = wiki.delete_user_note(rel)
        return _result(
            op="delete",
            rel_path=rel,
            path=str(path),
            wrote=True,
            changed=True,
            message=f"삭제했습니다.\n`{rel}`",
        )

    if op == "create":
        from iris.knowledge.wiki_filing import file_user_note

        filed = file_user_note(
            wiki,
            command.title or "새 노트",
            command.body or command.title or "새 노트",
            **filing,
        )
        return _result(
            op="create",
            rel_path=str(filed.get("rel_path") or ""),
            path=str(filed.get("path") or ""),
            title=command.title or "새 노트",
            wrote=True,
            changed=True,
            opened=True,
            mode="raw",
        )

    if op == "update":
        rel = _resolve(wiki, command)
        current = wiki.read_note(rel)
        title, source, article = article_from_note(current)
        new_title = (command.title or title or "untitled").strip()
        new_body = (command.body or article).strip()
        if not new_body:
            raise ValueError("본문이 비어 있습니다.")
        from iris.knowledge.wiki_filing import file_user_note

        filed = file_user_note(
            wiki,
            new_title,
            new_body,
            source_url=source,
            rel_path=rel,
            **{key: value for key, value in filing.items() if key != "classify"},
            classify=False,
        )
        return _result(
            op="update",
            rel_path=str(filed.get("rel_path") or rel),
            path=str(filed.get("path") or ""),
            title=new_title,
            wrote=True,
            changed=True,
            opened=True,
            mode="update",
        )

    raise ValueError(f"unknown wiki op: {op}")


def _check() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        source = root / "page.md"
        source.write_text("# Agents\n\nSkip this menu.\n\nWorkflows beat hidden loops.", encoding="utf-8")
        saved = execute_wiki_command(
            wiki,
            WikiCommand(op="save", source=str(source)),
        )
        assert saved["wrote"] and saved["mode"] == "raw"
        assert Path(saved["path"]).is_file()

        rel = str(saved["rel_path"])
        note = Path(saved["path"])
        note.write_text(
            "# Agents\n\n- source: https://example.com/a\n\n"
            "Building effective agents needs a workflow.\n\n"
            "The model should not claim it wrote the file.\n",
            encoding="utf-8",
        )

        def summarize(text: str) -> str:
            assert "workflow" in text
            return "한국어 요약: 워크플로가 필요하다."

        def translate(text: str) -> str:
            return "번역: " + text.split()[0]

        done = execute_wiki_command(
            wiki,
            WikiCommand(
                op="reprocess",
                rel_path=rel,
                keep_original=True,
                summarize=True,
                translate=True,
            ),
            summarize_fn=summarize,
            translate_fn=translate,
        )
        text = Path(done["path"]).read_text(encoding="utf-8")
        assert "한국어 요약" in text
        assert "Building effective agents" in text
        assert "> ko:" in text
        assert done["rel_path"] == rel

        opened = execute_wiki_command(wiki, WikiCommand(op="open", rel_path=rel))
        assert opened["opened"] and opened["rel_path"] == rel

        created = execute_wiki_command(
            wiki,
            WikiCommand(op="create", title="실험", body="본문이다"),
        )
        assert Path(created["path"]).is_file()
        updated = execute_wiki_command(
            wiki,
            WikiCommand(op="update", rel_path=created["rel_path"], title="바꾼제목"),
        )
        assert "바꾼제목" in Path(updated["path"]).read_text(encoding="utf-8")

        removed = execute_wiki_command(
            wiki,
            WikiCommand(op="delete", rel_path=created["rel_path"]),
        )
        assert removed["changed"] and not Path(removed["path"]).is_file()
        listed = execute_wiki_command(wiki, WikiCommand(op="list"))
        assert "Agents" in listed["message"]

    title, source_url, body = article_from_note(
        "# T\n\n## 정리\n\n요약\n\n## 원문\n\nHello.\n\n> ko: 안녕\n\nWorld.\n"
    )
    assert title == "T"
    assert "Hello." in body and "World." in body and "안녕" not in body
    assert source_url == ""
    print("wiki_ops ok")


if __name__ == "__main__":
    _check()
