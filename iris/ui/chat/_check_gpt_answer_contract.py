"""P3 실전 답변 계약 자검 — binary fence→matrix, plot merge, extract 신뢰도."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

_BACKTICK3 = "`" * 3


def _assert_normalize_binary_fences() -> None:
    from iris.ui.chat.gpt_answer_contract import normalize_binary_fences_for_display
    from iris.ui.chat.chat_renderer import render_iris_message
    from iris.ui.shared.theme_tokens import TOKENS

    plain = (
        "결과:\n\n"
        f"{_BACKTICK3}\n"
        "0 0 0\n"
        "0 1 0\n"
        "0 0 0\n"
        f"{_BACKTICK3}\n"
    )
    normalized = normalize_binary_fences_for_display(plain)
    assert "```matrix" in normalized, normalized
    assert normalized.count("```") >= 2

    # 이미 matrix면 유지
    already = f"{_BACKTICK3}matrix\n0 1\n1 0\n{_BACKTICK3}"
    assert normalize_binary_fences_for_display(already) == already

    # python 코드는 건드리지 않음
    py = f"{_BACKTICK3}python\nprint(0)\nprint(1)\n{_BACKTICK3}"
    assert normalize_binary_fences_for_display(py) == py

    one_bg = TOKENS.chat_matrix_one_bg
    html_out = render_iris_message(plain)
    assert "data-iris-matrix" in html_out, html_out[:400]
    assert f"background-color:{one_bg}" in html_out, html_out[:500]


def _assert_maybe_attach_plot() -> None:
    from iris.runtime.chat_code_exec import run_chat_python
    from iris.ui.chat.gpt_answer_contract import maybe_attach_plot_markdown
    from iris.ui.chat.chat_renderer import render_iris_message

    bare = "슬라이딩 윈도우 결과입니다."
    empty = maybe_attach_plot_markdown(bare, None)
    assert empty == bare
    empty2 = maybe_attach_plot_markdown(bare, {"ok": True, "chat_markdown": "", "png_paths": []})
    assert empty2 == bare

    result = run_chat_python(
        "import numpy as np\n"
        "import matplotlib.pyplot as plt\n"
        "plt.figure(figsize=(1.5,1.5)); plt.imshow([[0,1],[1,0]]); plt.axis('off')\n",
        timeout_s=30,
    )
    assert result.get("ok"), result
    merged = maybe_attach_plot_markdown(bare, result)
    assert "![" in merged, merged
    assert bare in merged
    # 이미 있으면 중복 안 함
    twice = maybe_attach_plot_markdown(merged, result)
    assert twice.count("![") == merged.count("![")

    html_out = render_iris_message(merged)
    assert "<img" in html_out, html_out[:400]


def _assert_extract_confidence() -> None:
    from iris.knowledge.grid_extract import (
        extract_binary_grid,
        extract_binary_grid_verdict,
        write_morphology_fixture,
        write_noisy_multi_grid_fixture,
    )

    with tempfile.TemporaryDirectory() as tmp:
        morph = Path(tmp) / "morph.png"
        write_morphology_fixture(morph)
        good = extract_binary_grid(morph)
        assert good is not None, "morphology fixture must stay GREEN"
        names = {g["name"] for g in good["grids"]}
        assert "image" in names and "kernel" in names, names
        assert not any(n.startswith("grid") for n in names), names
        verdict = extract_binary_grid_verdict(morph)
        assert verdict.ok and verdict.score >= 0.55, verdict
        assert verdict.data is not None

        noisy = Path(tmp) / "noisy.png"
        write_noisy_multi_grid_fixture(noisy)
        bad = extract_binary_grid(noisy)
        # 잡음 다수 grids를 그대로 내지 않는다
        if bad is not None:
            grids = bad.get("grids") or []
            assert len(grids) <= 3, grids
            assert not any(
                str(g.get("name") or "").startswith("grid") for g in grids
            ), [g.get("name") for g in grids]
        else:
            v = extract_binary_grid_verdict(noisy)
            assert not v.ok, v


def _assert_nudge_v24_examples() -> None:
    from iris.system import hermes_memory_nudge as nudge

    assert "iris-control-nudge-v25" in nudge._MARKER
    block = nudge._BLOCK
    assert "chat.exec_python" in block
    assert "```matrix" in block
    assert "WRONG" in block or "잘못된" in block
    assert "CORRECT" in block or "올바른" in block


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    # render_iris_message / math·문서 경로는 QApplication 필요 (없으면 0xC0000409)
    _app = QApplication.instance() or QApplication(sys.argv)
    _assert_normalize_binary_fences()
    _assert_maybe_attach_plot()
    _assert_extract_confidence()
    _assert_nudge_v24_examples()
    print("gpt_answer_contract ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
