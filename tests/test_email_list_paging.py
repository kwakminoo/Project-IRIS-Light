"""메일 목록 페이징·날짜 그룹 단위 테스트."""

from __future__ import annotations

from datetime import date

from iris.infrastructure.email_client import MAIL_PAGE_SIZE, _page_seqs
from iris.ui.workspaces.email_workspace_page import mail_date_group_label, mail_row_time_label


def test_mail_page_size_is_50() -> None:
    assert MAIL_PAGE_SIZE == 50


def test_page_seqs_newest_first_with_offset() -> None:
    # IMAP search 결과는 오래된 것 → 최신 순
    seqs = [str(i).encode() for i in range(1, 121)]  # 1..120
    page0 = _page_seqs(seqs, limit=50, offset=0)
    assert len(page0) == 50
    assert page0[0] == b"120"  # 최신
    assert page0[-1] == b"71"

    page1 = _page_seqs(seqs, limit=50, offset=50)
    assert len(page1) == 50
    assert page1[0] == b"70"
    assert page1[-1] == b"21"

    page2 = _page_seqs(seqs, limit=50, offset=100)
    assert len(page2) == 20
    assert page2[0] == b"20"
    assert page2[-1] == b"1"


def test_page_seqs_empty_and_bounds() -> None:
    assert _page_seqs([], limit=50, offset=0) == []
    assert _page_seqs([b"1", b"2"], limit=0, offset=0) == []
    assert _page_seqs([b"1", b"2"], limit=50, offset=10) == []


def test_mail_date_group_label() -> None:
    today = date(2026, 10, 18)
    assert mail_date_group_label("2026-10-18 09:30", today=today) == "오늘"
    assert mail_date_group_label("2026-10-17 23:00", today=today) == "어제"
    assert mail_date_group_label("2026-09-01 12:00", today=today) == "9월 1일"
    assert mail_date_group_label("2025-12-25 08:00", today=today) == "2025년 12월 25일"
    assert mail_date_group_label("weird", today=today) == "weird"


def test_mail_row_time_label() -> None:
    assert mail_row_time_label("2026-10-18 09:30") == "09:30"
    assert mail_row_time_label("bad") == "bad"
