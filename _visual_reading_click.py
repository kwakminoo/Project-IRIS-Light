import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPalette
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel

FENCE = "`" * 3
ANSWER = (
    "## IRIS 모듈 구조\n\n"
    "요청하신 내용을 **표**로 정리했습니다.\n\n"
    "| 모듈 | 역할 | 진입점 |\n"
    "|------|------|--------|\n"
    + "\n".join(f"| iris.module{i} | 역할 설명 {i} | `entry_{i}()` |" for i in range(18))
    + "\n\n### 코드 예시\n\n"
    f"{FENCE}python\n"
    + "\n".join(f"def handler_{i}(payload):\n    return payload * {i}" for i in range(10))
    + f"\n{FENCE}\n\n"
    "자세한 내용은 [문서](https://example.com/docs)를 참고하세요.\n"
)

app = QApplication.instance() or QApplication(sys.argv)
host = QWidget()
host.resize(1180, 820)
pal = host.palette()
pal.setColor(QPalette.ColorRole.Window, QColor("#050a14"))
host.setPalette(pal)
host.setAutoFillBackground(True)
lay = QVBoxLayout(host)
lay.setContentsMargins(0, 0, 0, 0)
panel = ChatPanel()
lay.addWidget(panel, 1)
host.show()
app.processEvents()

panel.append_message_instant("You", "IRIS 모듈 구조를 표로 정리해줘")
panel.append_message_instant("Iris", ANSWER)
app.processEvents()

log = panel._log
log.verticalScrollBar().setValue(0)
app.processEvents()
host.grab().save("_shot_full.png")

# 긴 답변 위 hover
found = log.document().find("역할 설명 3")
probe = log.textCursor()
probe.setPosition(found.selectionStart() + 2)
point = log.cursorRect(probe).center()
log.mouseMoveEvent(
    QMouseEvent(
        QEvent.Type.MouseMove,
        point.toPointF(),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
)
app.processEvents()
print("hover selections:", len(log.extraSelections()))
host.grab().save("_shot_hover.png")

region = log.reading_region_at(point)
print("region:", region)
panel.open_full_view(region.msg_id)
panel._reading_overlay.set_reveal_progress(1.0)
app.processEvents()
host.grab().save("_shot_reading.png")
print("panel geom:", panel._reading_overlay.panel.geometry())
