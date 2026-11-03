"""P0~P2 채팅 시각화 데모 — 매트릭스 표 + 구조화 격자 + matplotlib 플롯.

실행: .venv\\Scripts\\python.exe -m iris.ui._demo_gpt_chat_viz
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")


def _demo_answer() -> str:
    from iris.knowledge.grid_extract import (
        extract_binary_grid,
        format_grid_attachment_text,
        write_morphology_fixture,
    )
    from iris.runtime.chat_code_exec import run_chat_python

    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "morph.png"
        write_morphology_fixture(fixture)
        structured = extract_binary_grid(fixture) or {"grids": []}
        attach_preview = format_grid_attachment_text(structured)

    plot = run_chat_python(
        """
import numpy as np
import matplotlib.pyplot as plt
g = np.zeros((5, 5), dtype=int)
g[2, 2] = 1
plt.figure(figsize=(2.2, 2.2))
plt.imshow(g, cmap="Blues", vmin=0, vmax=1)
plt.title("Opening result")
plt.axis("off")
plt.tight_layout()
""",
        timeout_s=30,
    )
    plot_md = (plot.get("chat_markdown") or "").strip()

    return f"""이 문제는 모폴로지 Opening 예시입니다. Opening은 침식 후 팽창입니다.

$$A \\circ B = (A \\ominus B) \\oplus B$$

---

## 1단계. 침식(Erosion)

구조 요소(십자)가 모두 맞닿는 칸만 1이 남습니다.

```matrix
# 침식 결과
0 0 0 0 0
0 0 0 0 0
0 0 1 0 0
0 0 0 0 0
0 0 0 0 0
```

---

## 2단계. 팽창(Dilation)

침식 결과에 같은 커널로 팽창하면 Opening 결과가 됩니다.

```matrix
# Opening 결과
0 0 0 0 0
0 0 1 0 0
0 1 1 1 0
0 0 1 0 0
0 0 0 0 0
```

---

## 첨부에서 읽은 구조화 격자 (P1)

아래는 OCR이 아니라 `extract_binary_grid`가 넣은 입력입니다.

{attach_preview}

---

## 플롯 (P2 · chat.exec_python)

{plot_md}
"""


def main() -> int:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

    from iris.ui.chat.chat_panel import ChatPanel

    app = QApplication.instance() or QApplication(sys.argv)
    root = QWidget()
    root.setWindowTitle("Iris — GPT식 채팅 시각화 데모 (P0·P1·P2)")
    root.resize(520, 780)
    layout = QVBoxLayout(root)
    tip = QLabel(
        "아래는 구현된 표시 예시입니다. "
        "본 앱 채팅에서도 같은 Markdown(```matrix)과 chat.exec_python 플롯이 동작합니다.\n"
        "실전 확인 예: 컨볼루션 문제 PNG 첨부 + 「왜 이렇게 되는건지 설명해줘」 "
        "→ 색 matrix 표·(가능하면) 히트맵 PNG·잡음 gridN 나열 금지."
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color:#94a3b8;padding:8px 10px;font-size:12px;")
    layout.addWidget(tip)
    panel = ChatPanel()
    layout.addWidget(panel, 1)
    question = (
        "컴퓨터 비전 모폴로지 Opening 문제야. "
        "침식·팽창 단계를 ```matrix 격자로 보여줘."
    )
    panel.append_message_instant("You", question)
    panel.append_message_instant("Iris", _demo_answer())
    # 입력창에 이어서 보낼 문장 제시
    try:
        panel._input.setPlainText(
            "같은 방식으로 Closing도 ```matrix 로 풀어줘"
        )
    except Exception:
        pass
    root.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    root.show()
    root.raise_()
    root.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
