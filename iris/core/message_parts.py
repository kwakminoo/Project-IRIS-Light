"""Typed chat message parts — domain model + serde + display MD summary.

Owns: MessagePart frozen variants, parse/serialize, parts_display_md,
writing_context_snippets, parts_for_model.
Does not: UI, DB schema, ChatPanel, streaming.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

DisplayMode = Literal["inline", "pip", "fullscreen"]
_DISPLAY_MODES: frozenset[str] = frozenset({"inline", "pip", "fullscreen"})


@dataclass(frozen=True)
class TextPart:
    markdown: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class WritingPart:
    title: str
    body: str
    type: Literal["writing"] = "writing"


@dataclass(frozen=True)
class CodePart:
    language: str
    source: str
    filename: str = ""
    type: Literal["code"] = "code"


@dataclass(frozen=True)
class ToolPart:
    name: str
    detail: str = ""
    type: Literal["tool"] = "tool"


@dataclass(frozen=True)
class ToolShellPart:
    """Cursor-style shell / process card on the H1 transcript."""

    title: str
    command: str = ""
    output: str = ""
    status: str = "ok"
    block_id: str = ""
    collapsed: bool = False
    phase: str = "done"
    allow_always: bool = True
    type: Literal["tool_shell"] = "tool_shell"


@dataclass(frozen=True)
class ImagePart:
    alt: str = ""
    path: str = ""
    type: Literal["image"] = "image"


@dataclass(frozen=True)
class ExecutionPart:
    """Chat code-run result (stdout/stderr/ok). Images are separate ImageParts."""

    stdout: str = ""
    stderr: str = ""
    ok: bool = True
    language: str = "python"
    type: Literal["execution"] = "execution"


@dataclass(frozen=True)
class AppPart:
    title: str
    html: str
    display_mode: DisplayMode = "inline"
    type: Literal["app"] = "app"


@dataclass(frozen=True)
class CitationPart:
    label: str
    url: str = ""
    type: Literal["citation"] = "citation"


@dataclass(frozen=True)
class DiagramPart:
    """Archify / SpeakTools diagram.render landing (path to HTML + kind)."""

    path: str
    kind: str = ""
    title: str = ""
    type: Literal["diagram"] = "diagram"


MessagePart = (
    TextPart
    | WritingPart
    | CodePart
    | ToolPart
    | ToolShellPart
    | ImagePart
    | ExecutionPart
    | AppPart
    | CitationPart
    | DiagramPart
)


def _require_str(data: Mapping[str, Any], key: str, *, default: str | None = None) -> str:
    if key not in data:
        if default is not None:
            return default
        raise ValueError(f"missing field: {key}")
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"field {key} must be str")
    return value


def _require_bool(data: Mapping[str, Any], key: str, *, default: bool | None = None) -> bool:
    if key not in data:
        if default is not None:
            return default
        raise ValueError(f"missing field: {key}")
    value = data[key]
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "ok"):
            return True
        if low in ("false", "0", "no"):
            return False
    raise ValueError(f"field {key} must be bool")


def _parse_display_mode(data: Mapping[str, Any]) -> DisplayMode:
    raw = data.get("display_mode", data.get("displayMode", "inline"))
    if not isinstance(raw, str) or raw not in _DISPLAY_MODES:
        raise ValueError(f"invalid display_mode: {raw!r}")
    return raw  # type: ignore[return-value]


def parse_part(data: Mapping[str, Any]) -> MessagePart:
    if not isinstance(data, Mapping):
        raise ValueError("part must be a mapping")
    kind = data.get("type")
    if not isinstance(kind, str) or not kind:
        raise ValueError("missing or invalid type")
    if kind == "text":
        return TextPart(markdown=_require_str(data, "markdown"))
    if kind == "writing":
        return WritingPart(
            title=_require_str(data, "title"),
            body=_require_str(data, "body"),
        )
    if kind == "code":
        return CodePart(
            language=_require_str(data, "language"),
            source=_require_str(data, "source"),
            filename=_require_str(data, "filename", default=""),
        )
    if kind == "tool":
        return ToolPart(
            name=_require_str(data, "name"),
            detail=_require_str(data, "detail", default=""),
        )
    if kind == "tool_shell":
        return ToolShellPart(
            title=_require_str(data, "title"),
            command=_require_str(data, "command", default=""),
            output=_require_str(data, "output", default=""),
            status=_require_str(data, "status", default="ok"),
            block_id=_require_str(data, "block_id", default=""),
            collapsed=_require_bool(data, "collapsed", default=False),
            phase=_require_str(data, "phase", default="done"),
        )
    if kind == "image":
        return ImagePart(
            alt=_require_str(data, "alt", default=""),
            path=_require_str(data, "path", default=""),
        )
    if kind == "execution":
        return ExecutionPart(
            stdout=_require_str(data, "stdout", default=""),
            stderr=_require_str(data, "stderr", default=""),
            ok=_require_bool(data, "ok", default=True),
            language=_require_str(data, "language", default="python"),
        )
    if kind == "app":
        return AppPart(
            title=_require_str(data, "title"),
            html=_require_str(data, "html"),
            display_mode=_parse_display_mode(data),
        )
    if kind == "citation":
        return CitationPart(
            label=_require_str(data, "label"),
            url=_require_str(data, "url", default=""),
        )
    if kind == "diagram":
        return DiagramPart(
            path=_require_str(data, "path"),
            kind=_require_str(data, "kind", default=""),
            title=_require_str(data, "title", default=""),
        )
    raise ValueError(f"unknown part type: {kind!r}")


def parse_parts(data: Sequence[Any] | None) -> list[MessagePart]:
    if data is None:
        return []
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes)):
        raise ValueError("parts must be a sequence or None")
    return [parse_part(item) for item in data]


def part_to_dict(part: MessagePart) -> dict[str, Any]:
    if isinstance(part, TextPart):
        return {"type": "text", "markdown": part.markdown}
    if isinstance(part, WritingPart):
        return {"type": "writing", "title": part.title, "body": part.body}
    if isinstance(part, CodePart):
        return {
            "type": "code",
            "language": part.language,
            "source": part.source,
            "filename": part.filename,
        }
    if isinstance(part, ToolPart):
        return {"type": "tool", "name": part.name, "detail": part.detail}
    if isinstance(part, ToolShellPart):
        return {
            "type": "tool_shell",
            "title": part.title,
            "command": part.command,
            "output": part.output,
            "status": part.status,
            "block_id": part.block_id,
            "collapsed": part.collapsed,
            "phase": part.phase,
        }
    if isinstance(part, ImagePart):
        return {"type": "image", "alt": part.alt, "path": part.path}
    if isinstance(part, ExecutionPart):
        return {
            "type": "execution",
            "stdout": part.stdout,
            "stderr": part.stderr,
            "ok": part.ok,
            "language": part.language,
        }
    if isinstance(part, AppPart):
        return {
            "type": "app",
            "title": part.title,
            "html": part.html,
            "displayMode": part.display_mode,
        }
    if isinstance(part, CitationPart):
        return {"type": "citation", "label": part.label, "url": part.url}
    if isinstance(part, DiagramPart):
        return {
            "type": "diagram",
            "path": part.path,
            "kind": part.kind,
            "title": part.title,
        }
    raise ValueError(f"unsupported part: {type(part)!r}")


def parts_to_jsonable(parts: Sequence[MessagePart]) -> list[dict[str, Any]]:
    return [part_to_dict(part) for part in parts]


def _one_display_md(part: MessagePart) -> str:
    if isinstance(part, TextPart):
        return part.markdown
    if isinstance(part, WritingPart):
        return f"{part.title}\n\n{part.body}"
    if isinstance(part, CodePart):
        lang = part.language or ""
        return f"```{lang}\n{part.source}\n```"
    if isinstance(part, AppPart):
        return f"[app: {part.title}]"
    if isinstance(part, ToolPart):
        line = f"[tool: {part.name}]"
        if part.detail:
            line = f"{line} {part.detail}"
        return line
    if isinstance(part, ToolShellPart):
        cmd = (part.command or "").strip()
        return f"[shell: {part.title}] {cmd}".rstrip()
    if isinstance(part, ImagePart):
        if part.alt and part.path:
            return f"[image: {part.alt}] {part.path}"
        if part.alt:
            return f"[image: {part.alt}]"
        if part.path:
            return f"[image] {part.path}"
        return "[image]"
    if isinstance(part, ExecutionPart):
        status = "ok" if part.ok else "fail"
        chunks = [f"[execution: {status}]"]
        out = (part.stdout or "").rstrip()
        err = (part.stderr or "").rstrip()
        if out:
            chunks.append(out)
        if err:
            chunks.append(err)
        return "\n".join(chunks)
    if isinstance(part, CitationPart):
        line = f"[citation: {part.label}]"
        if part.url:
            line = f"{line} {part.url}"
        return line
    if isinstance(part, DiagramPart):
        label = (part.title or part.kind or "diagram").strip() or "diagram"
        line = f"[diagram: {label}]"
        if part.path:
            line = f"{line} {part.path}"
        return line
    raise ValueError(f"unsupported part: {type(part)!r}")


def parts_display_md(parts: Sequence[MessagePart]) -> str:
    if not parts:
        return ""
    return "\n\n".join(_one_display_md(part) for part in parts)


def writing_context_snippets(parts: Sequence[MessagePart]) -> str:
    """Saved WritingPart bodies for next-turn prompt injection."""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, WritingPart):
            continue
        title = (part.title or "").strip()
        body = (part.body or "").strip()
        if title and body:
            chunks.append(f"### {title}\n{body}")
        elif body:
            chunks.append(body)
        elif title:
            chunks.append(title)
    return "\n\n".join(chunks)


def parts_for_model(parts: Sequence[MessagePart]) -> str:
    """Flat text for next-turn prompts (includes saved WritingPart title/body)."""
    return parts_display_md(parts)
