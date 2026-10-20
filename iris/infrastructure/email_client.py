"""IMAP/SMTP 이메일 클라이언트 — Gmail·Naver·Daum·Yahoo·iCloud 자동 설정."""

from __future__ import annotations

import base64
import email
import imaplib
import re
import smtplib
import socket
import threading
import time
from dataclasses import dataclass
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from typing import Callable


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
    if domain == "naver.com":
        return MailServerConfig(
            imap_host="imap.naver.com",
            imap_port=993,
            smtp_host="smtp.naver.com",
            smtp_port=465,
            smtp_starttls=False,
        )
    if domain in ("daum.net", "hanmail.net"):
        return MailServerConfig(
            imap_host="imap.daum.net",
            imap_port=993,
            smtp_host="smtp.daum.net",
            smtp_port=465,
            smtp_starttls=False,
        )
    if domain in ("yahoo.com", "ymail.com"):
        return MailServerConfig(
            imap_host="imap.mail.yahoo.com",
            imap_port=993,
            smtp_host="smtp.mail.yahoo.com",
            smtp_port=587,
            smtp_starttls=True,
        )
    if domain in ("icloud.com", "me.com", "mac.com"):
        return MailServerConfig(
            imap_host="imap.mail.me.com",
            imap_port=993,
            smtp_host="smtp.mail.me.com",
            smtp_port=587,
            smtp_starttls=True,
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
    # timeout 없으면 부팅 점검(BootChecksWorker)이 이메일 단계에서 영구 대기할 수 있다.
    mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, timeout=30)
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


# 메일 목록 한 페이지 크기 (UI 무한 스크롤과 동일).
MAIL_PAGE_SIZE = 50
# RFC상 IDLE은 29분 전에 갱신. Gmail도 ~30분에서 끊김.
IDLE_REFRESH_SEC = 25 * 60
# IDLE 중 readline 타임아웃 — stop_event를 자주 확인.
IDLE_POLL_SEC = 30.0

_EXISTS_RE = re.compile(rb"^\* (\d+) EXISTS\s*$", re.IGNORECASE)


def _page_seqs(seqs: list[bytes], *, limit: int, offset: int) -> list[bytes]:
    """최신순으로 정렬한 뒤 offset부터 limit개만 반환."""
    if limit <= 0:
        return []
    start = max(0, offset)
    newest_first = list(reversed(seqs))
    return newest_first[start : start + limit]


def parse_exists_line(line: bytes) -> int | None:
    """`* N EXISTS` 언태그 응답에서 개수 추출."""
    m = _EXISTS_RE.match(line.strip())
    return int(m.group(1)) if m else None


def _summaries_from_seqs(
    mail: imaplib.IMAP4_SSL,
    seqs: list[bytes],
    *,
    use_recipient: bool = False,
) -> list[MailSummary]:
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


def _fetch_summaries(
    mail: imaplib.IMAP4_SSL,
    limit: int,
    criteria: tuple[str, ...],
    *,
    offset: int = 0,
    use_recipient: bool = False,
) -> list[MailSummary]:
    _status, data = mail.search(None, *criteria)
    if not data or not data[0]:
        return []
    seqs = _page_seqs(data[0].split(), limit=limit, offset=offset)
    return _summaries_from_seqs(mail, seqs, use_recipient=use_recipient)


def select_inbox_exists(mail: imaplib.IMAP4_SSL) -> int:
    typ, data = mail.select("INBOX")
    if typ != "OK" or not data or data[0] is None:
        raise ValueError("INBOX를 열 수 없습니다.")
    return int(data[0])


def fetch_summaries_seq_range(
    mail: imaplib.IMAP4_SSL,
    after_seq: int,
    new_exists: int,
    *,
    use_recipient: bool = False,
) -> list[MailSummary]:
    """after_seq 다음부터 new_exists까지 fetch. 반환은 최신순(prepend용)."""
    if new_exists <= after_seq:
        return []
    seqs = [str(i).encode("ascii") for i in range(after_seq + 1, new_exists + 1)]
    items = _summaries_from_seqs(mail, seqs, use_recipient=use_recipient)
    items.reverse()
    return items


def idle_wait_for_exists(
    mail: imaplib.IMAP4_SSL,
    known_exists: int,
    stop_event: threading.Event,
    *,
    refresh_sec: float = IDLE_REFRESH_SEC,
    poll_sec: float = IDLE_POLL_SEC,
    on_sock: Callable[[socket.socket | None], None] | None = None,
) -> tuple[str, int]:
    """
    IMAP IDLE로 EXISTS 증가·갱신·중단을 기다린다.

    Returns:
        ("exists", new_count) — 새 메일
        ("refresh", known) — 장시간 IDLE 갱신
        ("stop", known) — stop_event 또는 연결 종료
    """
    tag = mail._new_tag()
    mail.send(tag + b" IDLE\r\n")
    exists_now = known_exists
    # continuation (+)
    while True:
        if stop_event.is_set():
            _idle_done(mail, tag)
            return "stop", exists_now
        line = mail.readline()
        if not line:
            return "stop", exists_now
        n = parse_exists_line(line)
        if n is not None and n > exists_now:
            exists_now = n
        if line.startswith(b"+"):
            break

    sock = getattr(mail, "sock", None)
    if on_sock is not None:
        on_sock(sock if isinstance(sock, socket.socket) else None)

    started = time.monotonic()
    prev_timeout = None
    try:
        if isinstance(sock, socket.socket):
            prev_timeout = sock.gettimeout()
            sock.settimeout(poll_sec)
    except OSError:
        pass

    reason = "refresh"
    try:
        if exists_now > known_exists:
            reason = "exists"
        else:
            while True:
                if stop_event.is_set():
                    reason = "stop"
                    break
                if time.monotonic() - started >= refresh_sec:
                    reason = "refresh"
                    break
                try:
                    line = mail.readline()
                except socket.timeout:
                    continue
                except OSError:
                    return "stop", exists_now
                if not line:
                    return "stop", exists_now
                n = parse_exists_line(line)
                if n is not None and n > exists_now:
                    exists_now = n
                    reason = "exists"
                    break
        exists_now = _idle_done(mail, tag, exists_now)
        return reason, exists_now
    finally:
        try:
            if isinstance(sock, socket.socket) and prev_timeout is not None:
                sock.settimeout(prev_timeout)
        except OSError:
            pass
        if on_sock is not None:
            on_sock(None)


def _idle_done(
    mail: imaplib.IMAP4_SSL,
    tag: bytes,
    exists_now: int = 0,
) -> int:
    """DONE 전송 후 IDLE 태그 완료까지 읽고, 나온 EXISTS를 반영한다."""
    try:
        mail.send(b"DONE\r\n")
    except OSError:
        return exists_now
    while True:
        try:
            line = mail.readline()
        except (OSError, socket.timeout):
            return exists_now
        if not line:
            return exists_now
        n = parse_exists_line(line)
        if n is not None and n > exists_now:
            exists_now = n
        if line.startswith(tag + b" ") or line.startswith(tag + b"\r"):
            return exists_now


def run_inbox_idle_session(
    address: str,
    password: str,
    stop_event: threading.Event,
    *,
    on_new_mails: Callable[[list[MailSummary]], None],
    on_sock: Callable[[socket.socket | None], None] | None = None,
    config: MailServerConfig | None = None,
) -> None:
    """INBOX에 IDLE로 붙어 새 메일이 오면 on_new_mails(최신순) 호출. stop까지 유지."""
    cfg = config or detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        known = select_inbox_exists(mail)
        while not stop_event.is_set():
            reason, exists = idle_wait_for_exists(
                mail, known, stop_event, on_sock=on_sock
            )
            if reason == "stop":
                return
            if reason == "exists" and exists > known:
                items = fetch_summaries_seq_range(mail, known, exists)
                known = exists
                if items:
                    on_new_mails(items)
                continue
            # refresh: 재 SELECT 후 IDLE 재진입
            known = select_inbox_exists(mail)
    finally:
        if on_sock is not None:
            on_sock(None)
        try:
            mail.logout()
        except Exception:
            pass


def fetch_folder(
    address: str,
    password: str,
    folder_key: str = "inbox",
    *,
    limit: int = MAIL_PAGE_SIZE,
    offset: int = 0,
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
            offset=offset,
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
    limit: int = MAIL_PAGE_SIZE,
    offset: int = 0,
    config: MailServerConfig | None = None,
) -> list[MailSummary]:
    return fetch_folder(
        address, password, "inbox", limit=limit, offset=offset, config=config
    )


def fetch_gmail_category(
    address: str,
    password: str,
    category: str,
    *,
    limit: int = MAIL_PAGE_SIZE,
    offset: int = 0,
    config: MailServerConfig | None = None,
) -> list[MailSummary]:
    """Gmail 전용 — 받은편지함 내 카테고리(기본/프로모션/소셜/업데이트) 조회."""
    cfg = config or detect_mail_server(address)
    mail = _connect_imap(cfg, address, password)
    try:
        _select(mail, "INBOX")
        return _fetch_summaries(
            mail,
            limit,
            ("X-GM-RAW", f'"category:{category}"'),
            offset=offset,
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
_AGENT_INBOX_MAX = 25


def build_agent_context(
    account_address: str,
    message: "MailMessage | None",
    *,
    inbox: "list[MailSummary] | None" = None,
) -> str:
    """이메일 챗 → Hermes 에이전트에 주입할 시스템 컨텍스트.

    현재 계정·받은편지 요약·(열람 중이면) 메일 본문을 넣어
    '오늘 온 메일' / '이 메일 답장 초안'이 도구 없이도 바로 동작하게 한다.
    ponytail: 본문 2000자·받은편지 25통에서 자른다.
    """
    lines = [
        "너는 이메일 업무를 돕는 아이리스야. 기본 페르소나(SOUL)의 말투·판단 원칙을 따른다.",
        "메일 화면 조작·목록 조회는 Iris Control MCP(iris_invoke)를 쓴다: "
        "workspace.open_email, email.list_messages, email.read_message, "
        "email.refresh_inbox, email.open_message, email.open_compose, email.send. "
        "기본 화면/홈으로: workspace.open_assistant. "
        "마이크 끄기/켜기: voice.mic_off / voice.mic_on (또는 voice.toggle_mic). "
        "IDE Companion 종료만: ide.exit_companion.",
        "한국어로 간결하게 답하고, 목록에 없는 최신 메일이 필요하면 email.list_messages를 호출해.",
    ]
    addr = (account_address or "").strip()
    if addr:
        lines.append(f"현재 사용자 이메일 계정: {addr}")
    if inbox:
        lines.append("현재 화면에 불러온 받은편지(최신순):")
        for i, m in enumerate(inbox[:_AGENT_INBOX_MAX], 1):
            lines.append(
                f"{i}. [{m.date}] {m.sender} — {m.subject} (uid={m.uid})"
            )
            snip = (m.snippet or "").strip()
            if snip:
                lines.append(f"   요약: {snip[:100]}")
    if message is not None:
        body = (message.body or "").strip()[:_AGENT_BODY_MAX]
        lines += [
            "사용자가 지금 열람 중인 메일:",
            f"- uid: {message.uid}",
            f"- 제목: {message.subject}",
            f"- 보낸사람: {message.sender}",
            f"- 받는사람: {message.to}",
            f"- 날짜: {message.date}",
            "- 본문:",
            body,
        ]
    return "\n".join(lines)


def mail_summary_as_dict(m: MailSummary) -> dict:
    return {
        "uid": m.uid,
        "subject": m.subject,
        "sender": m.sender,
        "date": m.date,
        "snippet": m.snippet,
    }


def filter_summaries_since(
    items: list[MailSummary],
    since: str,
) -> list[MailSummary]:
    """since=YYYY-MM-DD (또는 YYYY-MM-DD HH:MM) — date 접두가 since 이상인 항목만."""
    needle = (since or "").strip()
    if not needle:
        return list(items)
    out: list[MailSummary] = []
    for m in items:
        d = (m.date or "").strip()
        if not d:
            continue
        # "2026-08-26 10:00" / "2026-08-26" 모두 since 날짜로 비교
        if d[: len(needle)] >= needle:
            out.append(m)
    return out


if __name__ == "__main__":
    assert detect_mail_server("a@gmail.com").imap_host == "imap.gmail.com"
    assert detect_mail_server("b@naver.com").smtp_port == 465
    assert detect_mail_server("c@hanmail.net").imap_host == "imap.daum.net"
    assert detect_mail_server("d@daum.net").smtp_host == "smtp.daum.net"
    assert detect_mail_server("e@yahoo.com").imap_host == "imap.mail.yahoo.com"
    assert detect_mail_server("f@icloud.com").imap_host == "imap.mail.me.com"
    assert detect_mail_server("g@me.com").smtp_host == "smtp.mail.me.com"

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
    # 본문만 2000자로 잘림 (프롬프트 다른 줄의 x는 무시)
    body_start = ctx_full.index("- 본문:\n") + len("- 본문:\n")
    assert ctx_full[body_start:].startswith("x" * _AGENT_BODY_MAX)
    assert len(ctx_full[body_start:].split("\n", 1)[0]) == _AGENT_BODY_MAX

    inbox_sample = [
        MailSummary("9", "오늘 메일", "a@b.com", "2026-08-26 09:00", "hello"),
        MailSummary("8", "어제 메일", "c@d.com", "2026-08-25 09:00", "old"),
    ]
    ctx_inbox = build_agent_context("me@gmail.com", None, inbox=inbox_sample)
    assert "오늘 메일" in ctx_inbox and "uid=9" in ctx_inbox
    today_only = filter_summaries_since(inbox_sample, "2026-08-26")
    assert len(today_only) == 1 and today_only[0].uid == "9"

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
    assert parse_exists_line(b"* 42 EXISTS") == 42
    assert parse_exists_line(b"* OK Still here") is None
    print("email_client ok")
