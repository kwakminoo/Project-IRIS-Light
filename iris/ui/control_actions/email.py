"""메일 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import EmailHost

def register_email_actions(window: EmailHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        _call_on_ui,
        _log,
        add_email_account,
        err_result,
        find_account,
        load_email_accounts,
        ok_result,
        remove_email_account,
    )

    def email_list(_a: dict[str, Any]) -> dict[str, Any]:
        items = [
            {"id": a.id, "address": a.address, "label": a.label}
            for a in load_email_accounts(window._db)
        ]
        return ok_result("email.list_accounts", {"accounts": items})

    def email_set_account(args: dict[str, Any]) -> dict[str, Any]:
        account_id = str(args.get("account_id") or "").strip()
        if not account_id or find_account(window._db, account_id) is None:
            return err_result("email.set_account", "valid account_id required")
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._on_email_account_changed(account_id)
        _log(window, "email.set_account", True)
        return ok_result("email.set_account", {"account_id": account_id})

    def email_select_folder(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("folder") or args.get("name") or "받은편지함").strip()
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._on_email_folder_selected(name)
        _log(window, "email.select_folder", True)
        return ok_result("email.select_folder", {"folder": name})

    def email_set_category(args: dict[str, Any]) -> dict[str, Any]:
        index = int(args.get("index") or 0)
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._on_email_category(index)
        _log(window, "email.set_category", True)
        return ok_result("email.set_category", {"index": index})

    def email_refresh(_a: dict[str, Any]) -> dict[str, Any]:
        if window._workspace_mode != "email":
            window._on_email_icon()
        else:
            window._refresh_email_inbox()
        _log(window, "email.refresh_inbox", True)
        return ok_result("email.refresh_inbox", {})

    def email_list_messages(args: dict[str, Any]) -> dict[str, Any]:
        """IMAP에서 목록을 가져와 Hermes가 요약할 수 있게 반환.

        ponytail: IMAP은 HTTP 워커(오프-UI)에서. UI 갱신만 _call_on_ui.
        기본은 화면 캐시 우선(응답 없음 방지). 강제 갱신은 refresh=true.
        """
        from datetime import date

        from iris.infrastructure.email_client import (
            filter_summaries_since,
            fetch_folder,
            fetch_gmail_category,
            mail_summary_as_dict,
        )
        from iris.storage.email_accounts import account_password

        def _snapshot() -> tuple[Any, str, str, list]:
            account = window._current_email_account()
            folder_default = str(getattr(window, "_email_folder", None) or "inbox")
            mode = str(getattr(window, "_workspace_mode", "") or "")
            cached: list = []
            if mode == "email":
                cached = list(window._email_page.current_mails())
            return account, folder_default, mode, cached

        snap = _call_on_ui(window, _snapshot)
        if not isinstance(snap, tuple):
            accounts = load_email_accounts(window._db)
            if not accounts:
                return err_result("email.list_messages", "no email account configured")
            account, folder_default, mode, cached = accounts[0], "inbox", "", []
        else:
            account, folder_default, mode, cached = snap
        if account is None:
            accounts = load_email_accounts(window._db)
            if not accounts:
                return err_result("email.list_messages", "no email account configured")
            account = accounts[0]

        folder = str(args.get("folder") or folder_default or "inbox").strip() or "inbox"
        category = str(args.get("category") or "").strip()
        limit = max(1, min(int(args.get("limit") or 40), 80))
        since = str(args.get("since") or "").strip()
        if str(args.get("today") or "").strip().lower() in {"1", "true", "yes"}:
            since = date.today().isoformat()
        force_refresh = str(args.get("refresh") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        # cached 기본 true — 화면에 이미 불러온 목록이면 IMAP 스킵
        cached_flag = str(args.get("cached") or "true").strip().lower()
        prefer_cache = (not force_refresh) and cached_flag not in {"0", "false", "no"}

        try:
            if prefer_cache and cached:
                items = list(cached)
            elif category:
                items = fetch_gmail_category(
                    account.address, account_password(account), category, limit=limit
                )
            else:
                items = fetch_folder(
                    account.address, account_password(account), folder, limit=limit
                )
            if since:
                items = filter_summaries_since(items, since)

            def _apply_ui() -> None:
                if window._workspace_mode != "email":
                    window._email_preloaded = True
                    window._on_email_icon()
                window._email_page.set_mails(items)

            _call_on_ui(window, _apply_ui)
            _log(window, "email.list_messages", True)
            return ok_result(
                "email.list_messages",
                {
                    "account": account.address,
                    "folder": folder,
                    "since": since,
                    "count": len(items),
                    "cached": bool(prefer_cache and cached),
                    "messages": [mail_summary_as_dict(m) for m in items],
                },
            )
        except Exception as exc:  # noqa: BLE001
            return err_result("email.list_messages", str(exc)[:240])

    def email_read_message(args: dict[str, Any]) -> dict[str, Any]:
        """본문 텍스트를 반환(에이전트 요약용). UI에도 연다.

        ponytail: IMAP은 오프-UI. 이미 받은 MailMessage로 show_message (이중 fetch 금지).
        """
        from iris.infrastructure.email_client import fetch_message
        from iris.storage.email_accounts import account_password

        uid = str(args.get("uid") or "").strip()
        if not uid:
            return err_result("email.read_message", "uid required")

        def _snapshot() -> tuple[Any, str]:
            account = window._current_email_account()
            folder = str(getattr(window, "_email_folder", None) or "inbox")
            return account, folder

        snap = _call_on_ui(window, _snapshot)
        if isinstance(snap, tuple):
            account, folder_default = snap
        else:
            accounts = load_email_accounts(window._db)
            account = accounts[0] if accounts else None
            folder_default = "inbox"
        if account is None:
            return err_result("email.read_message", "no email account configured")
        folder = str(args.get("folder") or folder_default or "inbox").strip() or "inbox"
        try:
            msg = fetch_message(
                account.address,
                account_password(account),
                uid,
                folder_key=folder,
            )

            def _apply_ui() -> None:
                if window._workspace_mode != "email":
                    window._email_preloaded = True
                    window._on_email_icon()
                window._email_page.show_message(msg)

            _call_on_ui(window, _apply_ui)
            body = (msg.body or "").strip()[:4000]
            _log(window, "email.read_message", True)
            return ok_result(
                "email.read_message",
                {
                    "uid": msg.uid,
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "to": msg.to,
                    "date": msg.date,
                    "body": body,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return err_result("email.read_message", str(exc)[:240])

    def email_open_message(args: dict[str, Any]) -> dict[str, Any]:
        uid = str(args.get("uid") or "").strip()
        if not uid:
            return err_result("email.open_message", "uid required")
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._load_email_message(uid)
        _log(window, "email.open_message", True)
        return ok_result("email.open_message", {"uid": uid})

    def email_open_compose(_a: dict[str, Any]) -> dict[str, Any]:
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._open_email_compose()
        _log(window, "email.open_compose", True)
        return ok_result("email.open_compose", {})

    def email_send(args: dict[str, Any]) -> dict[str, Any]:
        to = str(args.get("to") or "").strip()
        subject = str(args.get("subject") or "")
        body = str(args.get("body") or "")
        if not to:
            return err_result("email.send", "to required")
        if window._workspace_mode != "email":
            window._on_email_icon()
        window._send_email(to, subject, body)
        _log(window, "email.send", True)
        return ok_result("email.send", {"queued": True, "to": to})

    def email_add_account(args: dict[str, Any]) -> dict[str, Any]:
        address = str(args.get("address") or "").strip()
        password = str(args.get("password") or "")
        label = str(args.get("label") or "").strip()
        if not address or not password:
            return err_result("email.add_account", "address and password required")
        acc = add_email_account(window._db, address, password, label=label)
        _log(window, "email.add_account", True)
        return ok_result(
            "email.add_account",
            {"id": acc.id, "address": acc.address, "label": acc.label},
        )

    def email_remove_account(args: dict[str, Any]) -> dict[str, Any]:
        account_id = str(args.get("account_id") or "").strip()
        if not account_id:
            return err_result("email.remove_account", "account_id required")
        remove_email_account(window._db, account_id)
        if window._selected_email_account_id == account_id:
            window._selected_email_account_id = ""
        _log(window, "email.remove_account", True)
        return ok_result("email.remove_account", {"account_id": account_id})

    reg.register("email.list_accounts", email_list, summary="List email accounts (id/address/label, no passwords)")

    reg.register("email.set_account", email_set_account, summary="Select email account by id")

    reg.register(
        "email.select_folder",
        email_select_folder,
        summary="Select mailbox folder display name (받은편지함 등)",
    )

    reg.register("email.set_category", email_set_category, summary="Gmail category tab index")

    reg.register("email.refresh_inbox", email_refresh, summary="Refresh email inbox")

    reg.register(
        "email.list_messages",
        email_list_messages,
        summary="Fetch inbox summaries (optional since/today/limit/cached/refresh) for agent answers",
    )

    reg.register(
        "email.read_message",
        email_read_message,
        summary="Fetch email body by uid and open it in the UI",
    )

    reg.register("email.open_message", email_open_message, summary="Open email message by uid")

    reg.register("email.open_compose", email_open_compose, summary="Open email compose UI")

    reg.register(
        "email.send",
        email_send,
        summary="Send email (to, subject, body) — requires confirm=true",
        risk="high",
        confirm_required=True,
    )

    reg.register(
        "email.add_account",
        email_add_account,
        summary="Add email account (address, password, label) — requires confirm=true",
        risk="high",
        confirm_required=True,
    )

    reg.register(
        "email.remove_account",
        email_remove_account,
        summary="Remove email account by id — requires confirm=true",
        risk="high",
        confirm_required=True,
    )
