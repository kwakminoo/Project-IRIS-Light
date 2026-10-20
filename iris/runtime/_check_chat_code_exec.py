"""P2 chat.exec_python 자검 — matplotlib PNG + 채팅 markdown 렌더."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")


def main() -> int:
    from PyQt6.QtWidgets import QApplication
    import sys

    from iris.runtime.chat_code_exec import run_chat_python
    from iris.ui.chat.chat_renderer import render_iris_message

    code = """
import numpy as np
import matplotlib.pyplot as plt
g = np.zeros((5, 5), dtype=int)
g[2, 2] = 1
plt.figure(figsize=(2, 2))
plt.imshow(g, cmap='Blues', vmin=0, vmax=1)
plt.axis('off')
plt.tight_layout()
"""
    result = run_chat_python(code, timeout_s=30)
    assert result.get("ok") is True, result
    paths = result.get("png_paths") or []
    assert paths, result
    from pathlib import Path

    for p in paths:
        assert Path(p).is_file(), p
        assert Path(p).stat().st_size > 50, p

    md = result.get("chat_markdown") or ""
    assert "![" in md and paths[0].replace("\\", "/") in md.replace("\\", "/")

    app = QApplication.instance() or QApplication(sys.argv)
    html = render_iris_message("침식 결과\n\n" + md)
    assert "<img" in html, html[:300]
    src_ok = any(Path(p).name in html or p.replace("\\", "/") in html.replace("\\", "/") for p in paths)
    assert src_ok or "iris-image:" in html, html[:400]

    # 금지 import
    bad = run_chat_python("import os\nos.listdir('/')", timeout_s=5)
    assert bad.get("ok") is not True, bad

    print("chat_code_exec ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
