"""채팅 인용 칩 + 메시지 간 빈 줄 가독성 자검."""

from __future__ import annotations

import os
import sys

# offscreen — CI/헤드리스에서도 Qt 위젯 생성 가능
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from iris.core.chat_citations import iris_message_to_chat_html
from iris.ui.chat.chat_panel import ChatPanel

# 자료조사형 질문 10개 — 답변에 마크다운/베어 URL이 오면 칩으로 바뀌어야 함
RESEARCH_QA = [
    (
        "2024년 노벨 물리학상 수상자는 누구인가요?",
        "2024년 노벨 물리학상은 Hopfield와 Hinton에게 돌아갔습니다 "
        "[Nobel Prize](https://www.nobelprize.org/prizes/physics/2024/summary/).",
    ),
    (
        "파이썬 3.13의 주요 변경점은?",
        "자유 스레드(experimental)와 개선된 오류 메시지가 핵심입니다. "
        "https://docs.python.org/3.13/whatsnew/3.13.html",
    ),
    (
        "JWST가 최근 관측한 가장 먼 은하 후보는?",
        "후보 은하들은 NIRCam 심우주 관측에서 보고되었습니다 "
        "[NASA JWST](https://www.nasa.gov/mission_pages/webb/main/index.html).",
    ),
    (
        "한국의 최저시급 최근 고시 금액은?",
        "고용노동부 고시를 기준으로 확인하세요 "
        "[MOEL](https://www.moel.go.kr/).",
    ),
    (
        "Rust 2024 edition 안정화 상태는?",
        "Edition 안내: [The Rust Edition Guide](https://doc.rust-lang.org/edition-guide/).",
    ),
    (
        "OpenAI o3 모델 발표 요지는?",
        "공식 발표를 참고하세요 [OpenAI](https://openai.com/index/).",
    ),
    (
        "기후 IPCC AR6 요약 한 줄?",
        "요약본: [IPCC AR6](https://www.ipcc.ch/assessment-report/ar6/).",
    ),
    (
        "PostgreSQL 17 릴리스 노트 핵심은?",
        "릴리스 노트: https://www.postgresql.org/docs/17/release-17.html",
    ),
    (
        "WHO 팬데믹 협상 최근 진행은?",
        "현황: [WHO](https://www.who.int/).",
    ),
    (
        "Apple Silicon M4 공개 스펙 요약?",
        "제품 페이지: [Apple](https://www.apple.com/).",
    ),
]


def _assert_citations() -> None:
    for q, a in RESEARCH_QA:
        html_out = iris_message_to_chat_html(a)
        assert "href=" in html_out, f"no href for: {q}"
        assert "SOURCES" in html_out, f"no SOURCES footer for: {q}"
        assert "IRIS_CITE_" not in html_out, f"token leaked for: {q}"
    print(f"citations ok ({len(RESEARCH_QA)} research answers)")


def _assert_spacing(app: QApplication) -> None:
    panel = ChatPanel()
    panel.show()
    app.processEvents()
    for q, a in RESEARCH_QA[:3]:
        panel.append_message_instant("You", q)
        panel.append_message_instant("Iris", a)
        app.processEvents()
    plain = panel._log.toPlainText()
    # You/Iris 사이 빈 줄: "You: ...\n\nIris:" 패턴
    assert "\n\n" in plain, plain[:200]
    lines = plain.split("\n")
    # 메시지 블록 사이에 빈 줄이 하나 이상
    empties = sum(1 for i, line in enumerate(lines[:-1]) if line.strip() and not lines[i + 1].strip())
    assert empties >= 5, f"expected blank gaps after messages, got {empties}: {lines!r}"
    html_doc = panel._log.toHtml()
    assert "SOURCES" in html_doc or "href=" in html_doc
    print("spacing ok", empties, "blank gaps;", len(lines), "lines")


def main() -> int:
    _assert_citations()
    app = QApplication.instance() or QApplication(sys.argv)
    _assert_spacing(app)
    print("chat_citations_spacing ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
