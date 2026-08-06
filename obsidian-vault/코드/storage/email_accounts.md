# email_accounts

`iris/storage/email_accounts.py`

이메일 계정 — SQLite + 암호화 비밀번호.

## 주요 정의

- `class EmailAccount`
- `def _new_id`
- `def load_email_accounts`
- `def save_email_accounts`
- `def account_password`
- `def set_account_password`
- `def add_email_account`
- `def remove_email_account`
- `def find_account`

## 내부 의존성

- [[database]]
- [[secret_store]]
