"""Pygments 기반 fenced code 문법 강조 — Qt Rich Text용 인라인 style span 생성.

QTextEdit은 <style>/class 선택자를 신뢰할 수 없게 지원하므로 Pygments의
`noclasses=True` 출력(태그마다 인라인 style)만 사용한다. 실패하거나 지원하지
않는 언어면 None을 반환해 호출부가 기존 무채색 코드 블록으로 폴백하게 한다.
"""

from __future__ import annotations

from iris.ui.shared.theme_tokens import TOKENS

try:
    from pygments import highlight as _pygments_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.style import Style
    from pygments.token import (
        Comment,
        Error,
        Generic,
        Keyword,
        Name,
        Number,
        Operator,
        Punctuation,
        String,
        Token,
    )
    from pygments.util import ClassNotFound

    _PYGMENTS_AVAILABLE = True
except Exception:  # pragma: no cover - pygments 미설치 환경 대비 폴백
    _PYGMENTS_AVAILABLE = False

# Pygments가 기본 제공하지 않는 축약형만 보정한다. python/js/ts/sh/yml 등
# 대부분의 축약형은 Pygments가 이미 별칭(alias)으로 인식한다.
_LANGUAGE_ALIASES = {
    "kt": "kotlin",
}


def _build_style_class() -> type:
    syn = TOKENS.chat_syntax_colors

    class IrisChatSyntaxStyle(Style):
        background_color = None
        styles = {
            Token: TOKENS.text_primary,
            Comment: f"italic {syn['comment']}",
            Comment.Preproc: syn["comment"],
            Comment.Special: f"italic {syn['comment']}",
            Keyword: syn["keyword"],
            Keyword.Constant: syn["constant"],
            Keyword.Declaration: syn["keyword"],
            Keyword.Namespace: syn["keyword"],
            Keyword.Type: syn["builtin"],
            Name.Attribute: syn["attribute"],
            Name.Builtin: syn["builtin"],
            Name.Builtin.Pseudo: syn["constant"],
            Name.Class: syn["class_name"],
            Name.Constant: syn["constant"],
            Name.Decorator: syn["decorator"],
            Name.Entity: syn["tag"],
            Name.Exception: syn["class_name"],
            Name.Function: syn["function"],
            Name.Function.Magic: syn["function"],
            Name.Namespace: syn["class_name"],
            Name.Tag: syn["tag"],
            Name.Variable: syn["variable"],
            Name.Variable.Class: syn["variable"],
            Name.Variable.Global: syn["variable"],
            Name.Variable.Instance: syn["variable"],
            String: syn["string"],
            String.Doc: f"italic {syn['string']}",
            String.Escape: syn["constant"],
            String.Interpol: syn["constant"],
            Number: syn["number"],
            Operator: syn["operator"],
            Operator.Word: syn["keyword"],
            Punctuation: syn["punctuation"],
            Generic.Deleted: TOKENS.error,
            Generic.Inserted: syn["string"],
            Generic.Emph: "italic",
            Generic.Strong: "bold",
            Generic.Error: TOKENS.error,
            Error: TOKENS.error,
        }

    return IrisChatSyntaxStyle


_FORMATTER = (
    HtmlFormatter(style=_build_style_class(), noclasses=True, nowrap=True)
    if _PYGMENTS_AVAILABLE
    else None
)


def resolve_lexer_name(language: str) -> str:
    lang = (language or "").strip().lower()
    return _LANGUAGE_ALIASES.get(lang, lang)


def highlight_code(code: str, language: str) -> str | None:
    """언어에 맞는 Pygments 렉서가 있으면 강조된 HTML(span만, wrapper 없음)을
    반환하고, 없거나 실패하면 None을 반환한다. 공백·들여쓰기·줄바꿈은 그대로
    보존된다(stripnl/stripall/ensurenl 모두 비활성)."""
    if not _PYGMENTS_AVAILABLE:
        return None
    lang = resolve_lexer_name(language)
    if not lang:
        return None
    try:
        lexer = get_lexer_by_name(lang, stripnl=False, stripall=False, ensurenl=False)
    except ClassNotFound:
        return None
    try:
        result = _pygments_highlight(code or "", lexer, _FORMATTER)
    except Exception:
        return None
    # HtmlFormatter(nowrap=True)는 원본에 없던 trailing newline을 하나 덧붙이는
    # 경우가 있다(ensurenl=False로도 막히지 않음) — 원본에 없었다면 제거해
    # 줄바꿈이 강조 전후로 정확히 동일하게 유지되도록 한다.
    if result.endswith("\n") and not (code or "").endswith("\n"):
        result = result[:-1]
    return result


if __name__ == "__main__":
    out = highlight_code("def f(x):\n    return x + 1  # ok\n", "python")
    assert out is not None
    assert "def f(x):\n    return x + 1  # ok\n" not in out  # span으로 감싸져야 함
    assert out.count("\n") == 2, "줄바꿈 개수가 원본과 같아야 한다"
    assert highlight_code("x = 1", "no-such-language-xyz") is None
    assert highlight_code("x = 1", "") is None
    print("chat_syntax ok")
