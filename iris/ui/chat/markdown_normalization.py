"""Conservative display-only repair of model Markdown (never edit code)."""
from __future__ import annotations

import html
import re

_CODE = re.compile(r"(```[^\n]*\n[\s\S]*?(?:```|$)|~~~[^\n]*\n[\s\S]*?(?:~~~|$)|`[^`\n]+`)")
_ENTITY = re.compile(r"(?:&amp;)?&#(?:x[0-9a-fA-F]+|[0-9]+);|&amp;#(?:x[0-9a-fA-F]+|[0-9]+);")


def normalize_markdown_source(source: str) -> str:
    """Repair only unambiguous headings/list markers and numeric text entities.

    Decoding &lt; or &gt; here would turn escaped examples into executable HTML;
    numeric entities for those characters likewise stay escaped for the parser.
    """
    parts = _CODE.split((source or "").replace("\r\n", "\n"))
    for i in range(0, len(parts), 2):
        text = parts[i]
        # CommonMark hard breaks use backslash-newline; Python-Markdown's
        # nl2br extension otherwise leaves the escape visible. Never touch code.
        text = re.sub(r"(?<!\\)\\\n", "  \n", text)

        def decode(match: re.Match[str]) -> str:
            value = html.unescape(html.unescape(match[0]))
            return match[0] if any(ch in value for ch in "<>&") else value

        text = _ENTITY.sub(decode, text)
        text = re.sub(r"---(?=#{2,6})", "\n\n---\n\n", text)
        text = re.sub(r"(?<!#)(#{2,6})(?=[0-9가-힣])", r"\n\n\1 ", text)
        text = re.sub(r"(?m)(?<![\n#])(#{2,6})(?=\s+\S)", r"\n\n\1", text)
        text = re.sub(r"(?m)^(#{1,6}\s+[^\n]+)\n(?=\S)", r"\1\n\n", text)
        text = re.sub(r"(?m)^(\s*\d+\.)(?=\*\*|__)", r"\1 ", text)
        # Python-Markdown requires a blank line before lists and GFM tables.
        text = re.sub(r"(?m)([^\n])\n(?=(?:[-*+]\s+|\d+\.\s+)\S)", r"\1\n\n", text)
        text = re.sub(r"(?m)([^\n|])\n(?=\|[^\n]+\|\s*\n\|[ :|\-]+\|)", r"\1\n\n", text)
        parts[i] = text
    return "".join(parts)
