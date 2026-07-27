"""IMAP/SMTP 이메일 클라이언트 — Gmail·Naver 자동 설정."""

from __future__ import annotations

import base64
import email
import imaplib
import re
import smtplib
from dataclasses import dataclass
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime


@dataclass(frozen=True)
class MailServerConfig:
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    smtp_starttls: bool


@dataclass
class MailSummary:
    uid: str
    subject: str
    sender: str
    date: str
    snippet: str


@dataclass
class MailMessage:
    uid: str
    subject: str
    sender: str
    to: str
    date: str
    body: str  # 순수 텍스트(에이전트 컨텍스트용)
    html: str = ""  # 렌더링용 HTML(있으면 우선 표시)


def detect_mail_server(address: str) -> MailServerConfig:
    domain = address.rsplit("@", 1)[-1].lower()
    if domain in ("gmail.com", "googlemail.com"):
        return MailServerConfig(
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_starttls=True,
        )
    if domain in ("naver.com", "hanmail.net"):
        return MailServerConfig(
            imap_host="imap.naver.com",
            imap_port=993,
            smtp_host="smtp.naver.com",
            smtp_port=465,
            smtp_starttls=False,
        )
    return MailServerConfig(
        imap_host=f"imap.{domain}",
        imap_port=993,
        smtp_host=f"smtp.{domain}",
        smtp_port=587,
        smtp_starttls=True,
    )


def _decode_header_value(raw: str) -> str:
    if not raw:
        return ""
    parts: list[str] = []
    for chunk, enc in decode_header(raw):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return " ".join(parts).strip()


_TAG_RE = re.compile(r"<[^>]+>")


def _decode_part(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return str(payload or "")


def _extract_bodies(msg: email.message.Message) -> tuple[str, str]:
    """(plain, html) 본문을 추출한다. 첫 번째 text/plain·text/html을 각각 사용."""
    if not msg.is_multipart():
        text = _decode_part(msg)
        if msg.get_content_type() == "text/html":
            return "", text
        return text, ""
    plain, html_body = "", ""
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and not plain:
            plain = _decode_part(part)
        elif ctype == "text/html" and not html_body:
            html_body = _decode_part(part)
    return plain, html_body


def _collect_inline_images(msg: email.message.Message) -> dict[str, str]:
    """cid로 참조되는 인라인 이미지를 data URI로 변환해 매핑한다."""
    images: dict[str, str] = {}
    if not msg.is_multipart():
        return images
    for part in msg.walk():
        cid = part.get("Content-ID")
        ctype = part.get_content_type()
        if not cid or not ctype.startswith("image/"):
            continue
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            b64 = base64.b64encode(payload).decode("ascii")
            key = cid.strip().strip("<>")
            images[key] = f"data:{ctype};base64,{b64}"
    return images


def _inline_cid_images(html_body: str, images: dict[str, str]) -> str:
    for cid, data_uri in images.items():
        html_body = html_body.replace(f"cid:{cid}", data_uri)
    return html_body


def _html_to_text(html_body: str) -> str:
    return _TAG_RE.sub(" ", html_body).replace("&nbsp;", " ").strip()


def _connect_imap(config: MailServerConfig, address: str, password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
    mail.login(address, password)
    return mail


def is_gmail(address: str) -> bool:
    return address.rsplit("@", 1)[-1].lower() in ("gmail.com", "googlemail.com")


# 폴더 키 → IMAP SPECIAL-USE 플래그(RFC 6154). inbox는 항상 "INBOX".
_SPECIAL_USE = {
    "starred": "\\Flagged",
    "sent": "\\Sent",
    "drafts": "\\Drafts",
    "spam": "\\Junk",
    "trash": "\\Trash",
}
# Gmail 카테고리 탭 키(X-GM-RAW category:).
GMAIL_CATEGORIES = ("primary", "promotions", "social", "updates")

_LIST_RE = re.compile(rb"^\((?P<flags>[^)]*)\)\s+\S+\s+(?P<name>.+)$")


def _find_special_mailbox(mail: imaplib.IMAP4_SSL, special_flag: str) -> str | None:
    typ, data = mail.list()
    if typ != "OK" or not data:
        return None
    flag_b = special_flag.encode("ascii").lower()
    for line in data:
        if not isinstance(line, (bytes, bytearray)):
            continue
        m = _LIST_RE.match(bytes(line))
        if not m:
            continue
        if flag_b in m.group("flags").lower().split():
            name = m.group("name").strip()
            if name.startswith(b'"') and name.endswith(b'"'):
                name = name[1:-1]
            # 메일함 이름은 modified UTF-7(ASCII) — 그대로 select에 사용.
            return name.decode("ascii", errors="replace")
    return None


def _resolve_mailbox(mail: imaplib.IMAP4_SSL, folder_key: str) -> str:
    if folder_key in ("", "inbox"):
        return "INBOX"
    flag = _SPECIAL_USE.get(folder_key)
    if not flag:
        return "INBOX"
    found = _find_special_mailbox(mail, flag)
    if not found:
        raise ValueError(f"'{folder_key}' 폴더를 서버에서 찾을 수 없습니다.")
    return found


def _select(mail: imaplib.IMAP4_SSL, mailbox: str) -> None:
    quoted = mailbox if mailbox == "INBOX" else f'"{mailbox}"'
    typ, _ = mail.select(quoted)
    if typ != "OK":
        raise ValueError(f"메일함을 열 수 없습니다: {mailbox}")


def _fetch_summaries(
    mail: imaplib.IMAP4_SSL,
    limit: int,
    criteria: tuple[str, ...],
    *,
    use_recipient: bool = False,
) -> list[MailSummary]:
    _status, data = mail.search(None, *criteria)
    if not data or not data[0]:
        return []
    seqs = data[0].split()
    seqs = seqs[-limit:]
    seqs.reverse()
    out: list[MailSummary] = []
    for seq in seqs:
        _status, msg_data = mail.fetch(seq, "(RFC822)")
        if not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            continue
        msg = email.message_from_bytes(raw)
        subject = _decode_header_value(msg.get("Subject", ""))
        who = _decode_header_value(msg.get("To" if use_recipient else "From", ""))
        date_raw = msg.get("Date", "")
        try:
            date_str = parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OverflowError):
            date_str = date_raw
        plain, html_body = _extract_bodies(msg)
        snippet_src = plain or _html_to_text(html_body)
        snippet = snippet_src.replace("\r", " ").replace("\n", " ")[:120]
        out.append(
            MailSummary(
                uid=seq.decode("ascii", errors="replace"),
                subject=subject or "(제목 없음)",
                sender=who or "(주소 없음)",
                date=date_str,
                snippet=snippet,
            )
        )
    return out


def fetch_folder(
    address: str,
    password: str,
    folder_key: str = "inbox",
    *,
    limit: int = 40,
    config: MailServerConfig | None = None,
) -> list[MailSummary]:
    cfg = config or detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        mailbox = _resolve_mailbox(mail, folder_key)
        _select(mail, mailbox)
        return _fetch_summaries(
            mail,
            limit,
            ("ALL",),
            use_recipient=folder_key in ("sent", "drafts"),
        )
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def fetch_inbox(
    address: str,
    password: str,
    *,
    limit: int = 40,
    config: MailServerConfig | None = None,
) -> list[MailSummary]:
    return fetch_folder(address, password, "inbox", limit=limit, config=config)


def fetch_gmail_category(
    address: str,
    password: str,
    category: str,
    *,
    limit: int = 40,
    config: MailServerConfig | None = None,
) -> list[MailSummary]:
    """Gmail 전용 — 받은편지함 내 카테고리(기본/프로모션/소셜/업데이트) 조회."""
    cfg = config or detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        _select(mail, "INBOX")
        return _fetch_summaries(
            mail, limit, ("X-GM-RAW", f'"category:{category}"')
        )
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def fetch_message(
    address: str,
    password: str,
    uid: str,
    *,
    folder_key: str = "inbox",
    config: MailServerConfig | None = None,
) -> MailMessage:
    cfg = config or detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        _select(mail, _resolve_mailbox(mail, folder_key))
        _status, msg_data = mail.fetch(uid.encode("ascii"), "(RFC822)")
        if not msg_data or not msg_data[0]:
            raise ValueError("메일을 찾을 수 없습니다.")
        raw = msg_data[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            raise ValueError("메일 본문을 읽을 수 없습니다.")
        msg = email.message_from_bytes(raw)
        subject = _decode_header_value(msg.get("Subject", ""))
        sender = _decode_header_value(msg.get("From", ""))
        to = _decode_header_value(msg.get("To", ""))
        date_raw = msg.get("Date", "")
        try:
            date_str = parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OverflowError):
            date_str = date_raw
        plain, html_body = _extract_bodies(msg)
        if html_body:
            html_body = _inline_cid_images(html_body, _collect_inline_images(msg))
        text = plain or _html_to_text(html_body)
        return MailMessage(
            uid=uid,
            subject=subject or "(제목 없음)",
            sender=sender,
            to=to,
            date=date_str,
            body=text or "(본문 없음)",
            html=html_body,
        )
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def send_mail(
    address: str,
    password: str,
    to: str,
    subject: str,
    body: str,
    *,
    config: MailServerConfig | None = None,
) -> None:
    cfg = config or detect_mail_server(address)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = to
    if cfg.smtp_port == 465 and not cfg.smtp_starttls:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
            smtp.login(address, password)
            smtp.send_message(msg)
        return
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
        if cfg.smtp_starttls:
            smtp.starttls()
        smtp.login(address, password)
        smtp.send_message(msg)


def verify_login(address: str, password: str) -> None:
    cfg = detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        mail.select("INBOX")
    finally:
        mail.logout()


_AGENT_BODY_MAX = 2000


def build_agent_context(account_address: str, message: "MailMessage | None") -> str:
    """이메일 챗 → Hermes 에이전트에 주입할 시스템 컨텍스트.

    현재 계정과 (열람 중이면) 메일 본문을 요약해 '이 메일 답장 초안' 같은
    지시가 바로 동작하도록 한다. ponytail: 본문은 2000자에서 자른다(토큰 절약).
    """
    lines = [
        "너는 이메일 업무를 돕는 아이리스야. 헤르메스 에이전트의 이메일/웹/파일 도구를 사용할 수 있어.",
        "한국어로 간결하게 답하고, 메일 조회·요약·답장 초안·발송이 필요하면 도구를 사용해.",
    ]
    addr = (account_address or "").strip()
    if addr:
        lines.append(f"현재 사용자 이메일 계정: {addr}")
    if message is not None:
        body = (message.body or "").strip()[:_AGENT_BODY_MAX]
        lines += [
            "사용자가 지금 열람 중인 메일:",
            f"- 제목: {message.subject}",
            f"- 보낸사람: {message.sender}",
            f"- 받는사람: {message.to}",
            f"- 날짜: {message.date}",
            "- 본문:",
            body,
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    assert detect_mail_server("a@gmail.com").imap_host == "imap.gmail.com"
    assert detect_mail_server("b@naver.com").smtp_port == 465

    ctx_empty = build_agent_context("me@gmail.com", None)
    assert "me@gmail.com" in ctx_empty
    assert "열람 중인 메일" not in ctx_empty

    sample = MailMessage(
        uid="1",
        subject="회의 일정",
        sender="boss@corp.com",
        to="me@gmail.com",
        date="2026-07-21 10:00",
        body="x" * 5000,
    )
    ctx_full = build_agent_context("me@gmail.com", sample)
    assert "회의 일정" in ctx_full
    assert "boss@corp.com" in ctx_full
    # 본문은 2000자로 잘려야 한다
    assert ctx_full.count("x") == _AGENT_BODY_MAX

    # HTML 멀티파트에서 plain/html 분리 + cid 인라인 이미지 치환 검증
    from email.mime.image import MIMEImage
    from email.mime.multipart import MIMEMultipart

    related = MIMEMultipart("related")
    related.attach(MIMEText("<p>hi <img src='cid:img1'></p>", "html", "utf-8"))
    img = MIMEImage(b"\x89PNG\r\n", _subtype="png")
    img.add_header("Content-ID", "<img1>")
    related.attach(img)
    _plain, _html = _extract_bodies(related)
    assert "<img" in _html
    inlined = _inline_cid_images(_html, _collect_inline_images(related))
    assert "cid:img1" not in inlined and "data:image/png;base64," in inlined
    assert _html_to_text("<p>a<br>b</p>") == "a b" or "a" in _html_to_text("<p>a<br>b</p>")

    # IMAP LIST 응답에서 SPECIAL-USE 메일함 이름 파싱 검증
    class _FakeImap:
        def list(self):  # noqa: A003
            return "OK", [
                rb'(\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"',
                rb'(\HasNoChildren \Trash) "/" "[Gmail]/Trash"',
                rb'(\HasNoChildren) "/" "INBOX"',
            ]

    fake = _FakeImap()
    assert _find_special_mailbox(fake, "\\Sent") == "[Gmail]/Sent Mail"
    assert _find_special_mailbox(fake, "\\Trash") == "[Gmail]/Trash"
    assert _find_special_mailbox(fake, "\\Junk") is None
    assert is_gmail("a@gmail.com") and not is_gmail("b@naver.com")
    print("email_client ok")
