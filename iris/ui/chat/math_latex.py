"""채팅 LaTeX → 투명 PNG.

모델이 답변에 넣는 `$...$` / `$$...$$` 를 화면에서 조판한다.
스킬이나 툴이 아니다. 어떤 모델이 쓰든 구분자가 있으면 같은 경로로 그린다.
Qt 글 상자는 LaTeX를 못 그리므로, 수식만 이미지로 만들어 문장 사이에 넣는다.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
from dataclasses import dataclass
from pathlib import Path

_SCALE = 2
_DISPLAY_PX = 20
_INLINE_PX = 17
_TOKEN = "\ue014math{}\ue015"
_CACHE: dict[str, tuple[str, int, int]] = {}
_MATH_FENCE = re.compile(r"^```(?:math|latex|tex)\n([\s\S]*?)\n?```$", re.IGNORECASE)
_CODE = re.compile(
    r"(```[^\n]*\n[\s\S]*?(?:```|$)|~~~[^\n]*\n[\s\S]*?(?:~~~|$)|`[^`\n]+`)"
)
_BARE_ENV = re.compile(
    r"\\begin\{((?:bmatrix|pmatrix|Bmatrix|vmatrix|Vmatrix|matrix|aligned|align\*?|"
    r"cases|array|equation\*?))\}([\s\S]*?)\\end\{\1\}"
)

_BIN = {
    "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "ast": "∗", "star": "⋆",
    "div": "÷",
}
_REL = {
    "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈", "equiv": "≡", "sim": "∼",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "mapsto": "↦",
}
_ORD = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "sigma": "σ", "phi": "φ",
    "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Omega": "Ω",
    "infty": "∞", "partial": "∂", "nabla": "∇", "degree": "°", "circ": "°",
    "ldots": "…", "cdots": "⋯", "dots": "…", "prime": "′",
    "sum": "∑", "prod": "∏", "int": "∫",
}
_FENCE = {
    "bmatrix": ("[", "]"), "pmatrix": ("(", ")"), "Bmatrix": ("{", "}"),
    "vmatrix": ("|", "|"), "Vmatrix": ("‖", "‖"), "matrix": ("", ""),
    "aligned": ("", ""), "align": ("", ""), "align*": ("", ""),
    "cases": ("{", ""), "array": ("", ""),
}
_WRAP = {"equation", "equation*", "gather", "gather*"}
_ACCENT = {"overline", "underline", "hat", "bar", "vec", "dot", "ddot", "tilde", "widehat", "widetilde"}
_SKIP = {"displaystyle", "textstyle", "scriptstyle", "limits", "nolimits", "big", "Big", "bigg", "Bigg"}
_ROMAN_CMD = {"text", "mathrm", "mathbf", "operatorname", "mbox"}


@dataclass
class Metrics:
    w: int
    h: int
    d: int


def _cache_dir() -> Path:
    root = Path(os.environ.get("IRIS_MATH_CACHE", Path.home() / ".iris-light" / "math-cache"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _windows_fonts() -> Path:
    return Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def _load_font(px: int, *, korean: bool = False):
    from PIL import ImageFont

    fonts = _windows_fonts()
    if korean:
        for name in ("malgun.ttf", "malgunsl.ttf"):
            path = fonts / name
            if path.is_file():
                return ImageFont.truetype(str(path), px)
    math_font = fonts / "cambria.ttc"
    if math_font.is_file():
        return ImageFont.truetype(str(math_font), px, index=1)
    for name in ("times.ttf", "DejaVuSans.ttf"):
        path = fonts / name
        if path.is_file():
            return ImageFont.truetype(str(path), px)
    return ImageFont.load_default()


def _font(px: int, *, korean: bool = False):
    return _load_font(max(8, int(px)), korean=korean)


def _ascent(px: int) -> tuple[int, int]:
    return _font(px).getmetrics()


def _italic(text: str) -> str:
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr(0x1D44E + ord(ch) - 97))
        elif "A" <= ch <= "Z":
            out.append(chr(0x1D434 + ord(ch) - 65))
        else:
            out.append(ch)
    return "".join(out)


def _hangul(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


class Glyph:
    def __init__(self, text: str, px: int, *, roman: bool = False, kind: str = "ord") -> None:
        self.text = text
        self.px = px
        self.roman = roman
        self.kind = kind

    def _drawn(self) -> str:
        if self.roman or _hangul(self.text):
            return self.text
        return _italic(self.text)

    def _face(self):
        return _font(self.px, korean=_hangul(self.text))

    def metrics(self) -> Metrics:
        font = self._face()
        box = font.getbbox(self._drawn() or " ")
        ascent, descent = font.getmetrics()
        width = max(1, box[2] - min(0, box[0]) + 1)
        return Metrics(width, ascent, descent)

    def draw(self, mask, x: int, baseline: int) -> None:
        from PIL import ImageDraw

        font = self._face()
        box = font.getbbox(self._drawn() or " ")
        ImageDraw.Draw(mask).text(
            (x - min(0, box[0]), baseline - font.getmetrics()[0]),
            self._drawn(),
            font=font,
            fill=255,
        )


class Gap:
    def __init__(self, width: int, px: int) -> None:
        self.width = max(0, width)
        self.px = px
        self.kind = "gap"

    def metrics(self) -> Metrics:
        ascent, descent = _ascent(self.px)
        return Metrics(self.width, ascent, descent)

    def draw(self, mask, x: int, baseline: int) -> None:
        return None


class Frac:
    def __init__(self, num, den, px: int) -> None:
        self.num = num
        self.den = den
        self.px = px
        self.kind = "ord"

    def metrics(self) -> Metrics:
        num, den = self.num.metrics(), self.den.metrics()
        gap = max(2, self.px // 10)
        thick = max(1, self.px // 16)
        pad = max(4, self.px // 6)
        return Metrics(
            max(num.w, den.w) + pad,
            num.h + num.d + gap + thick,
            gap + den.h + den.d,
        )

    def draw(self, mask, x: int, baseline: int) -> None:
        from PIL import ImageDraw

        met = self.metrics()
        num, den = self.num.metrics(), self.den.metrics()
        gap = max(2, self.px // 10)
        thick = max(1, self.px // 16)
        bar = baseline - thick
        num_x = x + (met.w - num.w) // 2
        den_x = x + (met.w - den.w) // 2
        self.num.draw(mask, num_x, bar - gap - num.d)
        self.den.draw(mask, den_x, baseline + gap + den.h)
        ImageDraw.Draw(mask).line([(x, bar), (x + met.w, bar)], fill=255, width=thick)


class Script:
    def __init__(self, base, sup, sub, px: int) -> None:
        self.base = base
        self.sup = sup
        self.sub = sub
        self.px = px
        self.kind = "ord"

    def metrics(self) -> Metrics:
        base = self.base.metrics()
        sup = self.sup.metrics() if self.sup is not None else Metrics(0, 0, 0)
        sub = self.sub.metrics() if self.sub is not None else Metrics(0, 0, 0)
        rise = int(self.px * 0.40)
        drop = int(self.px * 0.18)
        return Metrics(
            base.w + max(sup.w, sub.w),
            max(base.h, rise + sup.h),
            max(base.d, drop + sub.d),
        )

    def draw(self, mask, x: int, baseline: int) -> None:
        base = self.base.metrics()
        self.base.draw(mask, x, baseline)
        if self.sup is not None:
            self.sup.draw(mask, x + base.w, baseline - int(self.px * 0.40))
        if self.sub is not None:
            sub = self.sub.metrics()
            self.sub.draw(mask, x + base.w, baseline + int(self.px * 0.18) + sub.h)


class Sqrt:
    def __init__(self, body, px: int) -> None:
        self.body = body
        self.px = px
        self.kind = "ord"

    def metrics(self) -> Metrics:
        body = self.body.metrics()
        rad = max(8, int(self.px * 0.62))
        extra = max(3, self.px // 8)
        return Metrics(rad + body.w + extra, body.h + extra, body.d)

    def draw(self, mask, x: int, baseline: int) -> None:
        from PIL import ImageDraw

        body = self.body.metrics()
        met = self.metrics()
        rad = max(8, int(self.px * 0.62))
        thick = max(2, self.px // 16)
        top = baseline - met.h
        dip = baseline + max(1, body.d // 3)
        mid_y = baseline - int(self.px * 0.15)
        draw = ImageDraw.Draw(mask)
        draw.line(
            [(x + 1, mid_y), (x + rad // 3, dip), (x + rad - 1, top + thick)],
            fill=255,
            width=thick,
        )
        draw.line([(x + rad - 1, top + thick), (x + met.w - 1, top + thick)], fill=255, width=thick)
        self.body.draw(mask, x + rad, baseline)


class Row:
    def __init__(self, items: list, px: int) -> None:
        self.items = _space_row(items, px)
        self.px = px
        self.kind = "ord"

    def metrics(self) -> Metrics:
        if not self.items:
            ascent, descent = _ascent(self.px)
            return Metrics(0, ascent, descent)
        width = 0
        height = 0
        depth = 0
        for item, gap in self.items:
            met = item.metrics()
            width += gap + met.w
            height = max(height, met.h)
            depth = max(depth, met.d)
        return Metrics(width, height, depth)

    def draw(self, mask, x: int, baseline: int) -> None:
        cursor = x
        for item, gap in self.items:
            cursor += gap
            item.draw(mask, cursor, baseline)
            cursor += item.metrics().w


class Matrix:
    def __init__(self, rows: list[list], left: str, right: str, px: int) -> None:
        self.rows = rows or [[]]
        self.left = left
        self.right = right
        self.px = px
        self.kind = "ord"

    def _grid(self) -> tuple[list[int], list[Metrics], int, int]:
        cols = max((len(row) for row in self.rows), default=1)
        col_w = [0] * cols
        row_m: list[Metrics] = []
        pad_x = max(6, int(self.px * 0.42))
        pad_y = max(3, int(self.px * 0.16))
        for row in self.rows:
            height = 0
            depth = 0
            for index in range(cols):
                cell = row[index] if index < len(row) else Gap(self.px // 2, self.px)
                met = cell.metrics()
                col_w[index] = max(col_w[index], met.w)
                height = max(height, met.h)
                depth = max(depth, met.d)
            row_m.append(Metrics(0, height + pad_y, depth + pad_y))
        inner_w = sum(col_w) + pad_x * max(0, cols - 1) + pad_x
        inner_h = sum(item.h + item.d for item in row_m)
        return col_w, row_m, inner_w, inner_h

    def metrics(self) -> Metrics:
        _cols, _rows, inner_w, inner_h = self._grid()
        ext = max(2, self.px // 8)
        left_w = _fence_width(inner_h + ext * 2, self.px) + max(4, self.px // 6) if self.left else max(2, self.px // 10)
        right_w = _fence_width(inner_h + ext * 2, self.px) + max(4, self.px // 6) if self.right else max(2, self.px // 10)
        return Metrics(left_w + inner_w + right_w, inner_h // 2 + ext, inner_h - inner_h // 2 + ext)

    def draw(self, mask, x: int, baseline: int) -> None:
        col_w, row_m, inner_w, inner_h = self._grid()
        met = self.metrics()
        ext = max(2, self.px // 8)
        top = baseline - met.h
        bot = baseline + met.d
        pad_x = max(6, int(self.px * 0.42))
        left_w = _fence_width(inner_h + ext * 2, self.px) + max(4, self.px // 6) if self.left else max(2, self.px // 10)
        if self.left:
            _draw_fence(mask, self.left, x, top, bot, self.px)
        if self.right:
            _draw_fence(mask, self.right, x + left_w + inner_w, top, bot, self.px, right=True)
        y = top + ext
        for r_index, row in enumerate(self.rows):
            cell_h = row_m[r_index].h + row_m[r_index].d
            cursor = x + left_w
            for c_index, width in enumerate(col_w):
                cell = row[c_index] if c_index < len(row) else Gap(1, self.px)
                cell_m = cell.metrics()
                cell_x = cursor + max(0, (width - cell_m.w) // 2)
                cell_base = y + (cell_h - (cell_m.h + cell_m.d)) // 2 + cell_m.h
                cell.draw(mask, cell_x, cell_base)
                cursor += width + pad_x
            y += cell_h


def _fence_width(height: int, px: int) -> int:
    return max(8, min(height // 10, px))


def _draw_fence(mask, kind: str, x: int, top: int, bot: int, px: int, *, right: bool = False) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(mask)
    thick = max(2, px // 14)
    arm = _fence_width(bot - top, px)
    if kind == "[":
        edge = x + arm - thick if right else x + thick
        serif_x = x if right else x + arm
        draw.line([(serif_x, top), (edge, top), (edge, bot), (serif_x, bot)], fill=255, width=thick)
    elif kind == "]":
        edge = x + thick
        draw.line([(x, top), (edge + arm, top), (edge + arm, bot), (x, bot)], fill=255, width=thick)
    elif kind == "(":
        draw.arc([x, top, x + arm * 2, bot], 90, 270, fill=255, width=thick)
    elif kind == ")":
        draw.arc([x - arm, top, x + arm, bot], 270, 90, fill=255, width=thick)
    elif kind == "{":
        mid = (top + bot) // 2
        draw.arc([x, top, x + arm, top + (mid - top)], 90, 180, fill=255, width=thick)
        draw.arc([x, mid, x + arm, bot], 180, 270, fill=255, width=thick)
    elif kind == "|":
        draw.line([(x + arm // 2, top), (x + arm // 2, bot)], fill=255, width=thick)
    elif kind == "‖":
        draw.line([(x + arm // 3, top), (x + arm // 3, bot)], fill=255, width=thick)
        draw.line([(x + 2 * arm // 3, top), (x + 2 * arm // 3, bot)], fill=255, width=thick)


def _space_row(items: list, px: int) -> list[tuple[object, int]]:
    spaced: list[tuple[object, int]] = []
    prev = ""
    bin_gap = max(3, int(px * 0.20))
    rel_gap = max(4, int(px * 0.28))
    for item in items:
        kind = getattr(item, "kind", "ord")
        gap = 0
        unary = kind in ("bin", "rel") and prev in ("", "open", "bin", "rel")
        if unary:
            kind = "ord"
        elif kind == "bin" and prev:
            gap = bin_gap
        elif kind == "rel" and prev:
            gap = rel_gap
        elif kind == "ord" and prev in ("bin", "rel"):
            gap = bin_gap if prev == "bin" else rel_gap
        elif kind == "punct":
            gap = 0
        spaced.append((item, gap))
        if kind == "punct":
            prev = "punct"
        else:
            prev = "ord" if unary else kind
        if kind == "punct":
            spaced.append((Gap(max(2, px // 8), px), 0))
            prev = "ord"
    return spaced


class Parser:
    def __init__(self, source: str, px: int) -> None:
        self.s = source
        self.n = len(source)
        self.i = 0
        self.px = px
        self.roman = False
        self.keep_space = False
        self.depth = 0
        self.matrix_depth = 0

    def parse(self):
        items = []
        while self.i < self.n:
            atom = self.parse_atom()
            if atom is None:
                if self.i < self.n:
                    self.i += 1
                continue
            items.append(atom)
        return _finish(items, self.px)

    def parse_atom(self):
        self._skip()
        if self.i >= self.n or self._at_cell_end():
            return None
        node = self._base()
        if node is None:
            return None
        return self._scripts(node)

    def _base(self):
        self._skip()
        if self.i >= self.n or self._at_cell_end():
            return None
        ch = self.s[self.i]
        if ch == "\\":
            return self._command()
        if ch == "{":
            return self._group(roman=False)
        if ch == "&":
            self.i += 1
            return Gap(self.px // 3, self.px)
        if ch == "}":
            return None
        return self._chars()

    def _chars(self):
        ch = self.s[self.i]
        if ch.isdigit() or (ch == "." and self.i + 1 < self.n and self.s[self.i + 1].isdigit()):
            j = self.i + 1
            while j < self.n and (self.s[j].isdigit() or self.s[j] == "."):
                j += 1
            text = self.s[self.i:j]
            self.i = j
            return Glyph(text, self.px, roman=True)
        if ch.isalpha():
            if self.roman:
                j = self.i + 1
                while j < self.n and self.s[j].isalpha():
                    j += 1
                text = self.s[self.i:j]
                self.i = j
                return Glyph(text, self.px, roman=True)
            self.i += 1
            return Glyph(ch, self.px, roman=False)
        self.i += 1
        if ch in "+-−":
            return Glyph("−" if ch in "-−" else "+", self.px, roman=True, kind="bin")
        if ch in "=<>":
            return Glyph(ch, self.px, roman=True, kind="rel")
        if ch in "([{":
            return Glyph(ch, self.px, roman=True, kind="open")
        if ch in ")]}":
            return Glyph(ch, self.px, roman=True, kind="close")
        if ch == ",":
            return Glyph(",", self.px, roman=True, kind="punct")
        if ch == "'":
            return Glyph("′", self.px, roman=True)
        if ch == "~":
            return Gap(self.px // 3, self.px)
        return Glyph(ch, self.px, roman=True)

    def _command(self):
        self.i += 1
        if self.i >= self.n:
            return None
        ch = self.s[self.i]
        if not ch.isalpha():
            self.i += 1
            if ch == "\\":
                return _BREAK
            if ch == ",":
                return Gap(max(2, self.px // 8), self.px)
            if ch in " ;:":
                return Gap(max(3, self.px // 5), self.px)
            if ch in "{}":
                return Glyph(ch, self.px, roman=True)
            return Glyph(ch, self.px, roman=True)
        j = self.i
        while j < self.n and self.s[j].isalpha():
            j += 1
        name = self.s[self.i:j]
        self.i = j
        if name == "begin":
            return self._begin()
        if name == "end":
            self._group_raw()
            return None
        if name in _SKIP:
            return Gap(0, self.px)
        if name == "left":
            return self._left()
        if name == "right":
            return None
        if name in _ROMAN_CMD:
            return self._group(roman=True)
        if name in ("frac", "dfrac", "tfrac"):
            return Frac(self._required(), self._required(), self.px)
        if name == "sqrt":
            if self.i < self.n and self.s[self.i] == "[":
                self._skip_brackets()
            return Sqrt(self._required(), self.px)
        if name in _ACCENT:
            return self._required()
        if name in _BIN:
            return Glyph(_BIN[name], self.px, roman=True, kind="bin")
        if name in _REL:
            return Glyph(_REL[name], self.px, roman=True, kind="rel")
        if name == "quad":
            return Gap(self.px, self.px)
        if name == "qquad":
            return Gap(self.px * 2, self.px)
        if name in _ORD:
            return Glyph(_ORD[name], self.px, roman=True)
        return self._required() if self.i < self.n and self.s[self.i] == "{" else Glyph(name, self.px, roman=True)

    def _begin(self):
        env = self._group_raw()
        if env == "array" and self.i < self.n and self.s[self.i] == "{":
            self._group_raw()
        if env in _FENCE:
            rows = self._matrix(env)
            left, right = _FENCE[env]
            return Matrix(rows, left, right, self.px)
        if env in _WRAP:
            return _finish(self._until_end(env), self.px)
        return _finish(self._until_end(env), self.px)

    def _matrix(self, env: str) -> list[list]:
        self.matrix_depth += 1
        rows: list[list] = []
        row: list = []
        cell: list = []
        while self.i < self.n:
            self._skip()
            if self._peek_end(env):
                self._consume_end(env)
                break
            if self.depth == 0 and self.i < self.n and self.s[self.i] == "&":
                self.i += 1
                row.append(_finish(cell, self.px))
                cell = []
                continue
            if self.depth == 0 and self.s.startswith("\\\\", self.i):
                self.i += 2
                row.append(_finish(cell, self.px))
                rows.append(row)
                row = []
                cell = []
                continue
            atom = self.parse_atom()
            if atom is None:
                if self._peek_end(env) or self.i >= self.n:
                    continue
                if self.i < self.n and (self.s[self.i] == "&" or self.s.startswith("\\\\", self.i)):
                    continue
                self.i += 1
                continue
            cell.append(atom)
        self.matrix_depth -= 1
        row.append(_finish(cell, self.px))
        rows.append(row)
        return rows or [[_finish([], self.px)]]

    def _until_end(self, env: str) -> list:
        items = []
        while self.i < self.n and not self._peek_end(env):
            atom = self.parse_atom()
            if atom is None:
                if self._peek_end(env) or self.i >= self.n:
                    break
                self.i += 1
                continue
            items.append(atom)
        self._consume_end(env)
        return items

    def _end_match(self, env: str) -> re.Match[str] | None:
        return re.match(rf"\\end\s*\{{{re.escape(env)}\}}", self.s[self.i:])

    def _peek_end(self, env: str) -> bool:
        return self._end_match(env) is not None

    def _consume_end(self, env: str) -> None:
        match = self._end_match(env)
        if match is not None:
            self.i += match.end()

    def _left(self):
        left = self._delim()
        items = []
        while self.i < self.n and not self.s.startswith("\\right", self.i):
            atom = self.parse_atom()
            if atom is None:
                if self.i < self.n and not self.s.startswith("\\right", self.i):
                    self.i += 1
                continue
            items.append(atom)
        right = ""
        if self.s.startswith("\\right", self.i):
            self.i += 6
            right = self._delim()
        return Matrix([[_finish(items, self.px)]], _norm_delim(left), _norm_delim(right), self.px)

    def _delim(self) -> str:
        self._skip()
        if self.i >= self.n:
            return ""
        if self.s[self.i] == "\\":
            self.i += 1
            if self.i < self.n and self.s[self.i] in "{}|.":
                ch = self.s[self.i]
                self.i += 1
                return "" if ch == "." else ch
            j = self.i
            while j < self.n and self.s[j].isalpha():
                j += 1
            self.i = j
            return ""
        ch = self.s[self.i]
        self.i += 1
        return "" if ch == "." else ch

    def _group(self, *, roman: bool):
        if self.i >= self.n or self.s[self.i] != "{":
            return self._required_atom()
        self.i += 1
        old_roman, old_space = self.roman, self.keep_space
        if roman:
            self.roman = True
            self.keep_space = True
        self.depth += 1
        items = []
        while self.i < self.n and self.s[self.i] != "}":
            atom = self.parse_atom()
            if atom is None:
                if self.i < self.n and self.s[self.i] != "}":
                    self.i += 1
                continue
            items.append(atom)
        if self.i < self.n and self.s[self.i] == "}":
            self.i += 1
        self.depth -= 1
        self.roman, self.keep_space = old_roman, old_space
        return _finish(items, self.px)

    def _required(self):
        self._skip()
        if self.i < self.n and self.s[self.i] == "{":
            return self._group(roman=False)
        node = self._base()
        return node if node is not None else Gap(0, self.px)

    def _required_atom(self):
        node = self._base()
        return node if node is not None else Gap(0, self.px)

    def _scripts(self, node):
        sup = sub = None
        while self.i < self.n and self.s[self.i] in "^_":
            kind = self.s[self.i]
            self.i += 1
            arg = self._script_arg()
            if kind == "^" and sup is None:
                sup = arg
            elif kind == "_" and sub is None:
                sub = arg
        if sup is None and sub is None:
            return node
        child = max(10, int(self.px * 0.62))
        return Script(node, _resize(sup, child), _resize(sub, child), self.px)

    def _script_arg(self):
        self._skip()
        if self.i < self.n and self.s[self.i] == "{":
            node = self._group(roman=False)
        else:
            node = self._base()
        return node if node is not None else Gap(0, self.px)

    def _group_raw(self) -> str:
        self._skip()
        if self.i >= self.n or self.s[self.i] != "{":
            return ""
        self.i += 1
        start = self.i
        while self.i < self.n and self.s[self.i] != "}":
            self.i += 1
        text = self.s[start:self.i]
        if self.i < self.n:
            self.i += 1
        return text

    def _skip_brackets(self) -> None:
        if self.i < self.n and self.s[self.i] == "[":
            self.i += 1
            while self.i < self.n and self.s[self.i] != "]":
                self.i += 1
            if self.i < self.n:
                self.i += 1

    def _skip(self) -> None:
        if self.keep_space:
            return
        while self.i < self.n and self.s[self.i] in " \t\r\n":
            self.i += 1

    def _at_cell_end(self) -> bool:
        if self.matrix_depth <= 0 or self.depth > 0 or self.i >= self.n:
            return False
        if self.s[self.i] == "&":
            return True
        if self.s.startswith("\\\\", self.i):
            return True
        return False


_BREAK = Glyph("", 1)


def _finish(items: list, px: int):
    flat = [item for item in items if item is not None and item is not _BREAK and not (isinstance(item, Glyph) and item.text == "" and item.px == 1)]
    rows: list[list] = [[]]
    for item in items:
        if item is _BREAK or (isinstance(item, Glyph) and item.text == "" and item.px == 1):
            rows.append([])
            continue
        if item is not None:
            rows[-1].append(item)
    if len(rows) > 1:
        return Matrix([[_finish(row, px)] for row in rows if row], "", "", px)
    return Row(flat, px)


def _resize(node, px: int):
    if node is None:
        return None
    if isinstance(node, (Glyph, Gap)):
        node.px = px
        return node
    if isinstance(node, Frac):
        node.px = px
        _resize(node.num, px)
        _resize(node.den, px)
        return node
    if isinstance(node, Script):
        node.px = px
        _resize(node.base, px)
        child = max(8, int(px * 0.70))
        _resize(node.sup, child)
        _resize(node.sub, child)
        return node
    if isinstance(node, Sqrt):
        node.px = px
        _resize(node.body, px)
        return node
    if isinstance(node, Row):
        node.px = px
        for item, _gap in node.items:
            _resize(item, px)
        return node
    if isinstance(node, Matrix):
        node.px = px
        for row in node.rows:
            for cell in row:
                _resize(cell, px)
        return node
    return node


def _norm_delim(ch: str) -> str:
    return {"(": "(", ")": ")", "[": "[", "]": "]", "{": "{", "}": "}", "|": "|"}.get(ch, ch if ch in "()[]{}|" else "")


def _paint(node, logical_px: int) -> tuple[bytes, int, int]:
    from PIL import Image

    px = logical_px * _SCALE
    _resize(node, px)
    if isinstance(node, Row):
        node.items = _space_row([item for item, _gap in node.items], px)
    met = node.metrics()
    pad = max(4, px // 8)
    width = max(1, met.w + pad * 2)
    height = max(1, met.h + met.d + pad * 2)
    mask = Image.new("L", (width, height), 0)
    node.draw(mask, pad, pad + met.h)
    red, green, blue = _ink()
    image = Image.new("RGBA", (width, height), (red, green, blue, 0))
    image.putalpha(mask)
    import io

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue(), max(1, width // _SCALE), max(1, height // _SCALE)


def _ink() -> tuple[int, int, int]:
    from iris.ui.shared.theme_tokens import TOKENS

    text = (TOKENS.chat_body or "#f8fafc").lstrip("#")
    if len(text) != 6:
        return (248, 250, 252)
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def render_math_png(latex: str, *, display: bool) -> tuple[str, int, int] | None:
    body = (latex or "").strip()
    if not body or len(body) > 8000:
        return None
    logical = _DISPLAY_PX if display else _INLINE_PX
    key = hashlib.sha256(f"{display}|{logical}|{_ink()}|{body}".encode("utf-8")).hexdigest()[:24]
    cached = _CACHE.get(key)
    if cached and Path(cached[0]).is_file():
        return cached
    try:
        node = Parser(body, logical * _SCALE).parse()
        data, width, height = _paint(node, logical)
    except Exception:
        return None
    if width < 2 or height < 2:
        return None
    path = _cache_dir() / f"{key}.png"
    path.write_bytes(data)
    shown_w, shown_h = width, height
    cap = 640 if display else 420
    if shown_w > cap:
        shown_h = max(1, int(shown_h * cap / shown_w))
        shown_w = cap
    found = (path.as_posix(), shown_w, shown_h)
    _CACHE[key] = found
    return found


def _alt(latex: str) -> str:
    text = re.sub(r"\\(?:begin|end)\{[^{}]*\}", " ", latex or "")
    text = re.sub(r"\\(?:text|mathrm|mathbf)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("{", "").replace("}", "").replace("&", " ").replace("\\\\", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return (text or "수식")[:120]


def _img(latex: str, *, display: bool) -> str | None:
    painted = render_math_png(latex, display=display)
    if painted is None:
        return None
    src, width, height = painted
    alt = html.escape(_alt(latex), quote=True)
    src_esc = html.escape(src, quote=True)
    align = "" if display else ' align="middle"'
    tag = f'<img src="{src_esc}" width="{width}" height="{height}" alt="{alt}"{align} />'
    if not display:
        return tag
    return f'<p align="center" style="margin-top:8px;margin-bottom:12px;">{tag}</p>'


def _is_inline_math(body: str) -> bool:
    value = body.strip()
    if not value or len(value) > 2000:
        return False
    if "\\" in value or "^" in value or "_" in value:
        return True
    if any(ch.isspace() for ch in value):
        return False
    return bool(re.fullmatch(r"[\w=+*/().,<>≤≥≠-]+", value))


def _escaped(text: str, index: int) -> bool:
    slashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slashes += 1
        cursor -= 1
    return slashes % 2 == 1


def _emit(body: str, *, display: bool, raw: str, formulas: list[tuple[str, str, bool]]) -> str:
    snippet = _img(body, display=display)
    if not snippet:
        return raw
    token = _TOKEN.format(len(formulas))
    formulas.append((token, snippet, display))
    if display:
        return f"\n\n{token}\n\n"
    return token


def _replace_prose(text: str, formulas: list[tuple[str, str, bool]]) -> str:
    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("$$", i) and not _escaped(text, i):
            close = text.find("$$", i + 2)
            if close < 0:
                parts.append(text[i:])
                break
            parts.append(_emit(text[i + 2:close], display=True, raw=text[i:close + 2], formulas=formulas))
            i = close + 2
            continue
        if text.startswith("\\[", i) and not _escaped(text, i):
            close = text.find("\\]", i + 2)
            if close < 0:
                parts.append(text[i:])
                break
            parts.append(_emit(text[i + 2:close], display=True, raw=text[i:close + 2], formulas=formulas))
            i = close + 2
            continue
        if text.startswith("\\(", i) and not _escaped(text, i):
            close = text.find("\\)", i + 2)
            if close < 0:
                parts.append(text[i:])
                break
            parts.append(_emit(text[i + 2:close], display=False, raw=text[i:close + 2], formulas=formulas))
            i = close + 2
            continue
        if text[i] == "$" and not _escaped(text, i):
            close = text.find("$", i + 1)
            if close < 0 or "\n" in text[i + 1:close]:
                parts.append("$")
                i += 1
                continue
            body = text[i + 1:close]
            if _is_inline_math(body):
                parts.append(_emit(body, display=False, raw=text[i:close + 1], formulas=formulas))
                i = close + 1
                continue
            parts.append("$")
            i += 1
            continue
        bare = _BARE_ENV.match(text, i)
        if bare and not _escaped(text, i):
            parts.append(_emit(bare.group(0), display=True, raw=bare.group(0), formulas=formulas))
            i = bare.end()
            continue
        parts.append(text[i])
        i += 1
    return "".join(parts)


def stash_chat_math(text: str) -> tuple[str, list[tuple[str, str, bool]]]:
    """코드 밖 수식만 토큰으로 바꾼다. 그리기에 실패하면 원문을 그대로 둔다."""
    formulas: list[tuple[str, str, bool]] = []
    parts = _CODE.split(text or "")
    for index, part in enumerate(parts):
        if index % 2 == 1:
            fence = _MATH_FENCE.match(part)
            if fence:
                parts[index] = _emit(fence.group(1), display=True, raw=part, formulas=formulas)
            continue
        parts[index] = _replace_prose(part, formulas)
    return "".join(parts), formulas


def restore_chat_math(html_body: str, formulas: list[tuple[str, str, bool]]) -> str:
    out = html_body or ""
    for token, snippet, display in formulas:
        if display:
            replaced, count = re.subn(
                rf"<p\b[^>]*>\s*{re.escape(token)}\s*</p>",
                snippet,
                out,
                count=1,
            )
            out = replaced if count else out.replace(token, snippet)
        else:
            out = out.replace(token, snippet)
    return out
