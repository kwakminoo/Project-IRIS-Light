# email_client

`iris/infrastructure/email_client.py`

IMAP/SMTP 이메일 클라이언트 — Gmail·Naver 자동 설정.

## 주요 정의

- `class MailServerConfig`
- `class MailSummary`
- `class MailMessage`
- `def detect_mail_server`
- `def _decode_header_value`
- `def _decode_part`
- `def _extract_bodies`
- `def _collect_inline_images`
- `def _inline_cid_images`
- `def _html_to_text`
- `def _connect_imap`
- `def is_gmail`
- `def _find_special_mailbox`
- `def _resolve_mailbox`
- `def _select`
- `def _fetch_summaries`
- `def fetch_folder`
- `def fetch_inbox`
- `def fetch_gmail_category`
- `def fetch_message`
- `def send_mail`
- `def verify_login`
- `def build_agent_context`
