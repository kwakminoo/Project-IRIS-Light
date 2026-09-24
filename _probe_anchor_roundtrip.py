import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QTextEdit

from iris.ui.chat.chat_renderer import render_iris_message

app = QApplication.instance() or QApplication(sys.argv)
edit = QTextEdit()

USER_PROP = 0x100000 + 7

cur = edit.textCursor()
cur.insertHtml('<a name="iris-msg-m1"><b>Iris</b></a>: ')
start = cur.position()
cur.insertHtml(render_iris_message("첫 답변 본문\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"))
cur.insertHtml('<a href="iris-tts://m1" style="color:#7dd3fc;text-decoration:none;">[재생]</a>')
end = cur.position()

cur.insertBlock()
cur.insertHtml('<a name="iris-msg-m2"><b>Iris</b></a>: 두번째 답변')
cur.insertHtml('<a href="iris-tts://m2" style="color:#7dd3fc;text-decoration:none;">[재생]</a>')

# 블록 포맷 커스텀 프로퍼티 태깅
tag = edit.textCursor()
tag.setPosition(start)
blk = tag.block()
fmt = blk.blockFormat()
fmt.setProperty(USER_PROP, "m1")
tag.setBlockFormat(fmt)


def scan_anchor_names(document):
    out = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                names = frag.charFormat().anchorNames()
                if names:
                    out.append((frag.position(), list(names)))
            it += 1
        block = block.next()
    return out


def scan_hrefs(document, needle):
    out = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                href = frag.charFormat().anchorHref()
                if needle in href:
                    out.append((frag.position(), href))
            it += 1
        block = block.next()
    return out


def block_props(document):
    out = []
    block = document.begin()
    while block.isValid():
        val = block.blockFormat().property(USER_PROP)
        if val:
            out.append((block.position(), val))
        block = block.next()
    return out


html_before = edit.toHtml()
print("=== BEFORE ===")
print("charCount", edit.document().characterCount())
print("anchor names in html:", 'name="iris-msg-m1"' in html_before)
print("anchorNames scan:", scan_anchor_names(edit.document()))
print("tts hrefs:", scan_hrefs(edit.document(), "iris-tts://"))
print("block props:", block_props(edit.document()))
print("plain len", len(edit.toPlainText()))

edit.setHtml(html_before)
print("=== AFTER setHtml roundtrip ===")
print("charCount", edit.document().characterCount())
print("anchorNames scan:", scan_anchor_names(edit.document()))
print("tts hrefs:", scan_hrefs(edit.document(), "iris-tts://"))
print("block props:", block_props(edit.document()))
print("plain len", len(edit.toPlainText()))

# 라벨 길이가 바뀌는 실제 set_speaker_status 시나리오
import re

changed = re.sub(
    r'(<a href="iris-tts://m1"[^>]*>)[^<]*(</a>)', r"\g<1>[생성중]\g<2>", html_before, count=1
)
edit.setHtml(changed)
print("=== AFTER label change (m1: [재생] -> [생성중]) ===")
print("anchorNames scan:", scan_anchor_names(edit.document()))
print("tts hrefs:", scan_hrefs(edit.document(), "iris-tts://"))
print("nested anchor test:")

# 중첩 <a> 지원 여부
e2 = QTextEdit()
e2.setHtml(
    '<a href="iris-msg://mX" style="color:#e8f0fe;text-decoration:none;">'
    'plain text <a href="https://example.com">link</a> more'
    "</a>"
)
print(scan_hrefs(e2.document(), "://"))
