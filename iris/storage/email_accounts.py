"""이메일 계정 — SQLite + 암호화 비밀번호."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from iris.storage.database import Database
from iris.storage.secret_store import decrypt_secret, encrypt_secret

EMAIL_ACCOUNTS_PREF_KEY = "email_accounts_v1"


@dataclass
class EmailAccount:
    id: str
    address: str
    password_enc: str = ""
    label: str = ""

    @property
    def display_name(self) -> str:
        label = (self.label or "").strip()
        if label:
            return f"{label} ({self.address})"
        return self.address


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def load_email_accounts(db: Database) -> list[EmailAccount]:
    raw = db.get_preference(EMAIL_ACCOUNTS_PREF_KEY, "")
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        out: list[EmailAccount] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            addr = str(item.get("address", "") or "").strip()
            if not addr:
                continue
            out.append(
                EmailAccount(
                    id=str(item.get("id") or _new_id()),
                    address=addr,
                    password_enc=str(item.get("password_enc") or ""),
                    label=str(item.get("label") or "").strip(),
                )
            )
        return out
    except (json.JSONDecodeError, TypeError):
        return []


def save_email_accounts(db: Database, accounts: list[EmailAccount]) -> None:
    payload = [
        {
            "id": a.id,
            "address": a.address,
            "password_enc": a.password_enc,
            "label": a.label,
        }
        for a in accounts
    ]
    db.set_preference(EMAIL_ACCOUNTS_PREF_KEY, json.dumps(payload, ensure_ascii=False))


def account_password(account: EmailAccount) -> str:
    return decrypt_secret(account.password_enc)


def set_account_password(account: EmailAccount, plain: str) -> None:
    account.password_enc = encrypt_secret(plain.strip())


def add_email_account(
    db: Database,
    address: str,
    password: str,
    *,
    label: str = "",
) -> EmailAccount:
    address = address.strip()
    accounts = load_email_accounts(db)
    for acc in accounts:
        if acc.address.lower() == address.lower():
            set_account_password(acc, password)
            if label.strip():
                acc.label = label.strip()
            save_email_accounts(db, accounts)
            return acc
    acc = EmailAccount(id=_new_id(), address=address, label=label.strip())
    set_account_password(acc, password)
    accounts.append(acc)
    save_email_accounts(db, accounts)
    return acc


def remove_email_account(db: Database, account_id: str) -> None:
    accounts = [a for a in load_email_accounts(db) if a.id != account_id]
    save_email_accounts(db, accounts)


def find_account(db: Database, account_id: str) -> EmailAccount | None:
    for acc in load_email_accounts(db):
        if acc.id == account_id:
            return acc
    return None
