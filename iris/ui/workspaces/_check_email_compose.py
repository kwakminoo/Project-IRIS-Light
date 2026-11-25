"""메일 작성 대화상자 — Qt6 StandardButton + parent=None 계약."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    from PyQt6.QtWidgets import QApplication, QDialogButtonBox

    app = QApplication.instance() or QApplication(sys.argv)

    # 계약: PyQt6에 Send 표준 버튼이 없다. 코드가 그걸 쓰면 즉시 실패해야 한다.
    assert not hasattr(
        QDialogButtonBox.StandardButton, "Send"
    ), "PyQt6 must not expose StandardButton.Send (regression probe)"

    from iris.storage.email_accounts import EmailAccount
    from iris.ui.workspaces import email_workspace_page as ewp
    from iris.ui.workspaces.email_workspace_page import _ComposeDialog

    # 소스 계약: Send 표준버튼 참조 금지 (주석의 금지 문구는 허용)
    src = open(ewp.__file__, encoding="utf-8").read()
    assert (
        "QDialogButtonBox.StandardButton.Send" not in src
    ), "email compose must not use QDialogButtonBox.StandardButton.Send"
    assert "QDialogButtonBox.StandardButton.Ok" in src or "QPushButton(" in src

    acc = EmailAccount(id="check", address="iris@example.com", password_enc="", label="check")
    dlg = _ComposeDialog(acc, None)
    assert dlg.parent() is None, "compose dialog parent must be None (frameless modal)"
    from PyQt6.QtWidgets import QPushButton

    labels = [b.text() for b in dlg.findChildren(QPushButton)]
    assert "보내기" in labels, labels
    assert any(t in ("Cancel", "취소") or "Cancel" in t or "취소" in t for t in labels), labels

    # open_compose는 exec 모달 — 생성 계약만 검증. 제어면은 실패 시 err_result.
    email_actions = open(
        os.path.join(os.path.dirname(__file__), "..", "control_actions", "email.py"),
        encoding="utf-8",
    ).read()
    compose_fn = email_actions.split("def email_open_compose")[1].split("def email_send")[0]
    assert "err_result" in compose_fn
    assert "ok_result" in compose_fn

    # parent=None 호출 경로 (EmailWorkspacePage.open_compose 소스)
    assert " _ComposeDialog(account, None)" in src or "_ComposeDialog(account, None)" in src

    dlg.close()
    print("email compose ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
