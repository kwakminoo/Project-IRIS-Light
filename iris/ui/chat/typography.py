"""Shared chat typography; persisted in the existing user_preferences table."""
from dataclasses import dataclass, asdict
import json
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QTextCursor, QTextFormat
from PyQt6.QtWidgets import QApplication
from iris.ui.shared.theme_tokens import TOKENS as THEME

KEY = "chat_typography_v1"
TYPING_CHARS_PER_SEC_MIN = 5
TYPING_CHARS_PER_SEC_MAX = 80
TYPING_CHARS_PER_SEC_DEFAULT = 20


@dataclass
class Typography:
    chat_font_family: str
    chat_font_size: int
    code_font_family: str
    code_font_size: int
    typing_chars_per_sec: int = TYPING_CHARS_PER_SEC_DEFAULT


def defaults():
    available = set(QFontDatabase.families())
    def choose(names, fallback):
        return next((n for n in names if n in available), fallback)
    app = QApplication.instance()
    ui = app.font()
    screen = app.primaryScreen()
    # Qt pixels are logical pixels: never multiply by devicePixelRatio again.
    ui_px = ui.pixelSize() if ui.pixelSize() > 0 else ui.pointSizeF() * screen.logicalDotsPerInch() / 72
    size = max(14, min(16, round(ui_px + 1)))
    return Typography(choose(["Pretendard", "Noto Sans KR", "Malgun Gothic", "맑은 고딕", "SUIT"], ui.family()),
                      size, choose(["JetBrains Mono", "Cascadia Mono", "Consolas"], QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()), size - 1)


def normalize(data):
    base = defaults()
    available = set(QFontDatabase.families())
    for key in ("chat_font_family", "code_font_family"):
        if data.get(key) in available:
            setattr(base, key, data[key])
    for key in ("chat_font_size", "code_font_size"):
        try:
            setattr(base, key, max(10, min(28, int(data.get(key, getattr(base, key))))))
        except (TypeError, ValueError, OverflowError):
            pass
    try:
        base.typing_chars_per_sec = max(
            TYPING_CHARS_PER_SEC_MIN,
            min(TYPING_CHARS_PER_SEC_MAX, int(data.get("typing_chars_per_sec", base.typing_chars_per_sec))),
        )
    except (TypeError, ValueError, OverflowError):
        pass
    return base


class TypographyManager(QObject):
    changed = pyqtSignal(object, object)

    def __init__(self):
        super().__init__()
        self.current = None

    def get(self):
        if self.current is None:
            self.current = defaults()
        return self.current

    def apply(self, prefs, db=None):
        prefs = normalize(asdict(prefs))
        old = self.get()
        if db is not None:
            db.set_preference(KEY, json.dumps(asdict(prefs), ensure_ascii=False))
        self.current = prefs
        if old != prefs:
            self.changed.emit(old, prefs)

    def load(self, db):
        try:
            data = json.loads(db.get_preference(KEY, "{}"))
        except (ValueError, TypeError):
            data = {}
        self.apply(normalize(data if isinstance(data, dict) else {}))


manager = TypographyManager()


def font(prefs=None):
    p = prefs or manager.get()
    f = QFont(p.chat_font_family)
    f.setPixelSize(p.chat_font_size)
    f.setWeight(QFont.Weight.Normal)
    f.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    return f


def family_css(family):
    # Safe inside style="...", including unusual installed family names.
    import html
    return html.escape("'" + family.replace("\\", "\\\\").replace("'", "\\'") + "'", quote=True)


class ChatTokens:
    def __getattr__(self, name):
        p = manager.get()
        values = {"chat_font_size": f"{p.chat_font_size}px",
                  "font_size_caption": f"{p.code_font_size}px",
                  "font_size_micro": f"{max(10, p.chat_font_size - 2)}px",
                  "chat_ui_font": family_css(p.chat_font_family),
                  "chat_block_mono_font": family_css(p.code_font_family),
                  "chat_block_code_weight": 400}
        return values[name] if name in values else getattr(THEME, name)


TOKENS = ChatTokens()


def normalize_headings(editor):
    """Qt applies HTML heading size adjustment even with an explicit CSS size."""
    doc = editor.document()
    block = doc.begin()
    edits = []
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                if fmt.hasProperty(QTextFormat.Property.FontSizeAdjustment):
                    level = block.blockFormat().headingLevel()
                    adjustment = int(fmt.property(QTextFormat.Property.FontSizeAdjustment))
                    offset = (4, 3, 2, 2, 1, 1)[level - 1] if level else {3: 4, 2: 3, 1: 2, 0: 2}.get(adjustment, 1)
                    fmt.clearProperty(QTextFormat.Property.FontSizeAdjustment)
                    f = fmt.font()
                    f.setPixelSize(manager.get().chat_font_size + offset)
                    fmt.setFont(f)
                    # Preserve heading identity when Qt merges it with a prefix block.
                    fmt.setProperty(int(QTextFormat.Property.UserProperty) + 732, offset)
                    edits.append((frag.position(), frag.length(), fmt))
            it += 1
        block = block.next()
    cursor = QTextCursor(doc)
    for pos, length, fmt in edits:
        cursor.setPosition(pos)
        cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)


def update_document(editor, old, new):
    """Reformat existing runs in place, preserving stream cursors, anchors and images."""
    doc = editor.document()
    bar = editor.verticalScrollBar()
    bottom = bar.value() >= bar.maximum() - 2
    scroll = bar.value()
    runs = []
    block = doc.begin()
    role_key = int(QTextFormat.Property.UserProperty) + 731
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                if not fmt.isImageFormat() and fmt.font().pixelSize() != 0:
                    role = fmt.property(role_key)
                    if not role:
                        families = fmt.fontFamilies() or []
                        mono = old.code_font_family in families
                        px = fmt.font().pixelSize()
                        role = "code" if mono else ("small" if 0 < px < old.chat_font_size else "body")
                    heading = block.blockFormat().headingLevel()
                    heading_offset = fmt.property(int(QTextFormat.Property.UserProperty) + 732)
                    size = new.code_font_size if role == "code" else (max(10, new.chat_font_size - 2) if role == "small" else new.chat_font_size)
                    if heading and role != "code":
                        size = new.chat_font_size + (4, 3, 2, 2, 1, 1)[heading - 1]
                    elif heading_offset and role != "code":
                        size = new.chat_font_size + int(heading_offset)
                    f = fmt.font()
                    f.setFamily(new.code_font_family if role == "code" else new.chat_font_family)
                    f.setPixelSize(size)
                    fmt.setFont(f)
                    fmt.clearProperty(QTextFormat.Property.FontSizeAdjustment)
                    fmt.setProperty(role_key, role)
                    runs.append((frag.position(), frag.length(), fmt))
            it += 1
        block = block.next()
    cursor = QTextCursor(doc)
    cursor.beginEditBlock()
    for pos, length, fmt in runs:
        cursor.setPosition(pos)
        cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)
    cursor.endEditBlock()
    editor.setFont(font(new))
    doc.setDefaultFont(font(new))
    bar.setValue(bar.maximum() if bottom else scroll)
