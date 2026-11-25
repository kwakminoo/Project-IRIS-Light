"""메일 작성 대화상자 — draft 프리필 · Send 버튼 · parent=None · send 분리.

계약:
- PyQt6 StandardButton.Send 없음 → Ok|Cancel (Ok 라벨 보내기)
- compose draft args (to/cc/bcc/subject/body) apply to dialog fields
- email.open_compose / email.compose_draft must not call _send_email / send_mail
- email.send stays confirm_required (HUD); no RequestApprovalLedger fingerprint for email

GAP (documented): email.send uses per-invoke HUD human_confirm. Args shown at
confirm are the args executed in that invoke. There is no reusable approval
ledger binding for email.send — if subject/body/recipients change, a new
invoke + new HUD confirm is required. RequestApprovalLedger is not wired here.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

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
    from iris.ui.workspaces.email_workspace_page import EmailWorkspacePage, _ComposeDialog

    # 소스 계약: Send 표준버튼 참조 금지 (주석의 금지 문구는 허용)
    src = open(ewp.__file__, encoding="utf-8").read()
    assert (
        "QDialogButtonBox.StandardButton.Send" not in src
    ), "email compose must not use QDialogButtonBox.StandardButton.Send"
    assert "QDialogButtonBox.StandardButton.Ok" in src or "QPushButton(" in src

    acc = EmailAccount(id="check", address="iris@example.com", password_enc="", label="check")
    draft = {
        "to": "alice@example.com",
        "cc": "bob@example.com",
        "bcc": "carol@example.com",
        "subject": "FPR-10 draft",
        "body": "hello draft body",
    }
    dlg = _ComposeDialog(acc, None, draft=draft)
    assert dlg.parent() is None, "compose dialog parent must be None (frameless modal)"
    fields = dlg.draft_fields()
    assert fields["to"] == draft["to"], fields
    assert fields["cc"] == draft["cc"], fields
    assert fields["bcc"] == draft["bcc"], fields
    assert fields["subject"] == draft["subject"], fields
    assert fields["body"] == draft["body"], fields

    from PyQt6.QtWidgets import QPushButton

    labels = [b.text() for b in dlg.findChildren(QPushButton)]
    assert "보내기" in labels, labels
    assert any(t in ("Cancel", "취소") or "Cancel" in t or "취소" in t for t in labels), labels

    page = EmailWorkspacePage()
    requested: list[tuple[str, str, str]] = []
    page.compose_requested.connect(lambda *fields: requested.append(fields))
    with patch.object(_ComposeDialog, "exec", side_effect=AssertionError("opening a draft must return immediately")):
        assert page.open_compose(acc, draft=draft)
    compose = page._compose_dialog
    assert compose is not None and compose.isVisible()
    assert compose.draft_fields() == draft
    assert requested == []
    compose.reject()
    assert requested == [] and page._compose_dialog is None

    email_actions_path = os.path.join(
        os.path.dirname(__file__), "..", "control_actions", "email.py"
    )
    email_actions = open(email_actions_path, encoding="utf-8").read()
    compose_fn = email_actions.split("def email_open_compose")[1].split("def email_compose_draft")[0]
    assert "err_result" in compose_fn
    assert "ok_result" in compose_fn
    assert "_send_email" not in compose_fn
    assert "send_mail" not in compose_fn
    assert "draft" in compose_fn
    assert 'sent": False' in compose_fn or "'sent': False" in compose_fn

    draft_fn = email_actions.split("def email_compose_draft")[1].split("def email_send")[0]
    assert "email_open_compose" in draft_fn
    assert "_send_email" not in draft_fn

    send_reg = email_actions.split('reg.register(\n        "email.send"')[1].split("reg.register")[0]
    assert "confirm_required=True" in send_reg

    # parent=None 호출 경로 (EmailWorkspacePage.open_compose 소스)
    assert " _ComposeDialog(account, None)" in src or "_ComposeDialog(account, None" in src
    assert "draft=draft" in src

    # Headless: apply_draft path does not invoke send workers.
    send_calls: list[tuple] = []

    class _FakePage:
        def open_compose(self, account, draft=None):  # noqa: ANN001
            d = _ComposeDialog(account, None, draft=draft)
            got = d.draft_fields()
            d.close()
            return got

    class _FakeWindow:
        _workspace_mode = "email"
        _email_page = _FakePage()

        def _on_email_icon(self) -> None:
            return None

        def _open_email_compose(self, draft=None):  # noqa: ANN001
            return self._email_page.open_compose(acc, draft=draft)

        def _send_email(self, to, subject, body) -> None:  # noqa: ANN001
            send_calls.append((to, subject, body))

    from iris.system.control_surface import ActionRegistry
    from iris.ui.control_actions.email import register_email_actions

    reg = ActionRegistry()
    register_email_actions(_FakeWindow(), reg)  # type: ignore[arg-type]
    # Bypass account/UI open: invoke compose_draft logic via dialog-only fake.
    out_fields = _FakeWindow()._open_email_compose(draft=draft)
    assert out_fields["to"] == draft["to"]
    assert out_fields["body"] == draft["body"]
    assert send_calls == [], f"compose draft must not send: {send_calls}"

    # Registry: compose_draft registered; send still confirm_required.
    catalog = reg.catalog()
    names = {s["name"] for s in catalog}
    assert "email.open_compose" in names
    assert "email.compose_draft" in names
    assert "email.send" in names
    send_spec = next(s for s in catalog if s["name"] == "email.send")
    assert send_spec.get("confirm_required") is True

    dlg.close()
    print("email compose ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
