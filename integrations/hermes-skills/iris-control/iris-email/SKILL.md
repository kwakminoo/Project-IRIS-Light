---
name: iris-email
description: >
  Open Iris Light email workspace, list/summarize inbox, read messages,
  compose and send mail via Iris Agent native tools + Control catalog.
  Use when: 메일 열어, 이메일 화면, 오늘 온 메일, 받은편지함 요약,
  이 메일 읽어, 답장 초안, open email, list inbox, today's mail.
---

# Iris email

## Prefer native seed tools

- Accounts (no passwords): `email_list_accounts`.
- Catalog / live UI state: `get_catalog` / `get_state` when needed.
- Inbox read/send still use Control actions (`email.list_messages`, …) via the product
  tool path — never invent Gmail web clicks or claim you read mail without tool results.
  Action IDs in this skill use dots; the callable function names use underscores.

## Steps

1. `email_list_accounts` — note account `id` / `address` / `label`.
2. Open UI if needed:
   `workspace_open_email` with `{}`
3. List mail (for "오늘 온 메일", "받은편지 요약"):
   `email_list_messages`
   args examples:
   - `{today: true}` — today only (uses UI cache by default — fast, no freeze)
   - `{since: "YYYY-MM-DD", limit: 40}`
   - `{refresh: true}` — force fresh IMAP (slower; only when cache is stale)
4. Read body:
   `email_read_message` args `{uid}`
   (also opens the message in Iris UI)
5. Compose / send:
   - `email_open_compose`
   - `email_send` args `{to, subject, body}` — high risk, needs human confirmation

## Notes

- Accounts come from Iris settings (Gmail/Naver app passwords). No passwords in tool output.
- After `email.list_messages`, summarize subject/sender/date in Korean.
- Never say "메일이 없습니다" without an empty `messages` list from the tool.
- Prefer the email workspace right-side Iris chat for mail tasks; main chat also works.
