"""IMAP/SMTP 이메일 클라이언트 — Gmail·Naver 자동 설정."""

from __future__ import annotations

import email
import imaplib
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
    body: str


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


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return str(payload or "")


def _connect_imap(config: MailServerConfig, address: str, password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
    mail.login(address, password)
    return mail


def fetch_inbox(
    address: str,
    password: str,
    *,
    limit: int = 40,
    config: MailServerConfig | None = None,
) -> list[MailSummary]:
    cfg = config or detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        mail.select("INBOX")
        _status, data = mail.search(None, "ALL")
        if not data or not data[0]:
            return []
        uids = data[0].split()
        uids = uids[-limit:]
        uids.reverse()
        out: list[MailSummary] = []
        for uid in uids:
            _status, msg_data = mail.fetch(uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            subject = _decode_header_value(msg.get("Subject", ""))
            sender = _decode_header_value(msg.get("From", ""))
            date_raw = msg.get("Date", "")
            try:
                date_str = parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError, OverflowError):
                date_str = date_raw
            body = _extract_body(msg)
            snippet = body.replace("\r", " ").replace("\n", " ")[:120]
            out.append(
                MailSummary(
                    uid=uid.decode("ascii", errors="replace"),
                    subject=subject or "(제목 없음)",
                    sender=sender or "(발신자 없음)",
                    date=date_str,
                    snippet=snippet,
                )
            )
        return out
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
    config: MailServerConfig | None = None,
) -> MailMessage:
    cfg = config or detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        mail.select("INBOX")
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
        body = _extract_body(msg)
        return MailMessage(
            uid=uid,
            subject=subject or "(제목 없음)",
            sender=sender,
            to=to,
            date=date_str,
            body=body or "(본문 없음)",
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


if __name__ == "__main__":
    assert detect_mail_server("a@gmail.com").imap_host == "imap.gmail.com"
    assert detect_mail_server("b@naver.com").smtp_port == 465
    print("email_client ok")
