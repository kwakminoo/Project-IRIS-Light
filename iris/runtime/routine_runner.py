"""루틴을 언제 돌릴지 고르고, 결과를 어떻게 알릴지 다듬는다.

여기엔 네트워크도 Qt도 없다. "지금 돌릴 게 뭔가"와 "무엇을 보여줄 것인가"만
계산한다. 실제 호출은 `RoutineRunWorker`, 화면 반영은 MainWindow 가 한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from iris.runtime.routine_schedule import (
    OUTCOME_MISSED,
    DueCheck,
    check_due,
)
from iris.storage.database import Database
from iris.storage.routines import (
    STATUS_FAILED,
    STATUS_MISSED,
    STATUS_OK,
    Routine,
    list_routines,
    mark_ran,
)

# 한 틱에 이보다 많이 돌리지 않는다. 오래 꺼뒀다 켜면 한꺼번에 몰리기 때문이다.
MAX_PER_TICK = 2


@dataclass(frozen=True)
class DueRoutine:
    routine: Routine
    check: DueCheck

    @property
    def is_missed(self) -> bool:
        return self.check.outcome == OUTCOME_MISSED


def collect_due(
    db: Database, now: datetime | None = None, *, limit: int = MAX_PER_TICK
) -> tuple[list[DueRoutine], list[DueRoutine]]:
    """(지금 돌릴 것, 놓쳐서 건너뛸 것).

    놓친 것에는 개수 제한을 두지 않는다 — 실행이 아니라 기록만 하면 되고,
    밀린 걸 남겨두면 다음 틱에 또 판단해야 해서 깔끔하지 않다.
    """
    moment = now or datetime.now()
    run_now: list[DueRoutine] = []
    missed: list[DueRoutine] = []
    for routine in list_routines(db, enabled_only=True):
        if not routine.next_run_at:
            continue
        check = check_due(routine.next_run_at, moment)
        if check.outcome == OUTCOME_MISSED:
            missed.append(DueRoutine(routine=routine, check=check))
        elif check.should_run and len(run_now) < max(1, int(limit)):
            run_now.append(DueRoutine(routine=routine, check=check))
    return run_now, missed


def reschedule(
    db: Database, routine: Routine, now: datetime | None = None
) -> str:
    """다음 실행 시각을 계산한다. 더 돌 일이 없으면 빈 문자열(once 소진)."""
    moment = now or datetime.now()
    nxt = routine.schedule.next_after(moment)
    return nxt.isoformat(timespec="seconds") if nxt else ""


def record_missed(
    db: Database, due: DueRoutine, now: datetime | None = None
) -> Routine | None:
    """놓친 회차를 기록하고 다음으로 넘긴다. 실행 횟수로는 세지 않는다."""
    return mark_ran(
        db,
        due.routine.id,
        status=STATUS_MISSED,
        result=due.check.note(),
        next_run_at=reschedule(db, due.routine, now),
    )


def record_result(
    db: Database,
    due: DueRoutine,
    *,
    text: str = "",
    error: str = "",
    now: datetime | None = None,
) -> Routine | None:
    body = (error or text or "").strip()
    note = due.check.note()
    if note:
        body = f"{body}\n\n_{note}_" if body else note
    return mark_ran(
        db,
        due.routine.id,
        status=STATUS_FAILED if error else STATUS_OK,
        result=body,
        next_run_at=reschedule(db, due.routine, now),
    )


def build_run_messages(
    routine: Routine,
    *,
    evidence: str = "",
    tools_available: bool = True,
) -> list[dict[str, str]]:
    """루틴 실행 요청. 사용자가 말한 문장을 그대로 시킨다.

    미리 액션으로 쪼개 두면 사용자가 말한 뉘앙스("한 줄씩", "3개만")를 잃는다.
    대신 이게 예약 실행이라는 것과 결과만 달라는 것을 시스템 메시지로 못박는다.

    `tools_available=False` 면 **웹에 못 닿는다는 사실을 모델에게 알린다.**
    실측 결과 이 문장이 없으면 "오늘 뉴스 3개"에 그럴듯한 가짜 헤드라인을 지어낸다
    — 모델은 자기가 검색을 못 한다는 걸 스스로 알지 못하기 때문이다.
    """
    system = [
        "너는 아이리스다. 지금은 사용자가 예약해 둔 반복 작업을 실행하는 중이다.",
        f"작업 이름: {routine.name}",
        f"주기: {routine.schedule.describe()}",
        "",
        "규칙:",
        "- 사용자가 지금 옆에 없을 수 있다. 되묻지 말고 가능한 선에서 끝내라.",
        "- 결과만 내라. '알겠습니다' 같은 서두나 예약 작업이라는 설명은 붙이지 마라.",
        "- 사용자가 요청한 개수·형식을 정확히 지켜라.",
        "- 정보를 못 구했으면 지어내지 말고 무엇을 못 구했는지 한 줄로 밝혀라.",
    ]
    if not tools_available:
        system.extend(
            [
                "",
                "지금 웹 검색·브라우징·외부 API 를 쓸 수 없다.",
                "뉴스·날씨·주가·환율·스포츠 결과처럼 지금 시각의 정보가 필요하면 "
                "확인하지 못한 사실을 결과처럼 적지 마라.",
                "학습된 지식만으로 끝낼 수 있는 일(계산·번역·요약·글쓰기)은 그대로 하라.",
            ]
        )
    if evidence.strip():
        system.extend(["", "참고할 과거 기록:", evidence.strip()])
    return [
        {"role": "system", "content": "\n".join(system)},
        {"role": "user", "content": routine.task},
    ]


def format_delivery(routine: Routine, text: str, check: DueCheck) -> str:
    """채팅·알림에 내보낼 본문. 늦었으면 사실을 앞에 붙인다."""
    body = (text or "").strip() or "(결과 없음)"
    note = check.note()
    head = f"**{routine.name}**"
    if note:
        return f"{head}\n\n_{note}_\n\n{body}"
    return f"{head}\n\n{body}"


def notify_summary(routine: Routine, text: str, *, limit: int = 120) -> str:
    """알림 팝업용 짧은 한 줄 — 팝업은 길면 잘린다."""
    flat = " ".join((text or "").split())
    if not flat:
        return "결과 없음"
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from iris.storage.routines import create_routine, get_routine, update_routine

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "rr.db")
        base = datetime(2026, 9, 29, 8, 0)

        news = create_routine(
            db, name="아침 뉴스", task="뉴스 3개 정리해줘", time_of_day="09:00", now=base
        )
        assert news.next_run_at == "2026-09-29T09:00:00"

        # 아직 시각 전
        run_now, missed = collect_due(db, datetime(2026, 9, 29, 8, 30))
        assert run_now == [] and missed == []

        # 정시
        run_now, missed = collect_due(db, datetime(2026, 9, 29, 9, 0))
        assert len(run_now) == 1 and run_now[0].routine.id == news.id
        assert run_now[0].check.note() == ""

        # 30분 늦음 — 따라잡는다
        run_now, _ = collect_due(db, datetime(2026, 9, 29, 9, 30))
        assert run_now and run_now[0].check.outcome == "late"
        assert "30분 늦게" in run_now[0].check.note()

        # 하루 지남 — 건너뛴다
        run_now, missed = collect_due(db, datetime(2026, 9, 30, 12, 0))
        assert run_now == [] and len(missed) == 1
        assert missed[0].is_missed

        after = record_missed(db, missed[0], datetime(2026, 9, 30, 12, 0))
        assert after.miss_count == 1 and after.run_count == 0
        assert after.next_run_at == "2026-10-01T09:00:00", after.next_run_at
        assert "건너뛰었습니다" in after.last_result

        # 성공 기록
        run_now, _ = collect_due(db, datetime(2026, 10, 1, 9, 0))
        assert run_now
        done = record_result(db, run_now[0], text="1. A\n2. B\n3. C", now=datetime(2026, 10, 1, 9, 0))
        assert done.run_count == 1 and done.last_status == STATUS_OK
        assert "1. A" in done.last_result
        assert done.next_run_at == "2026-10-02T09:00:00"

        # 실패 기록
        run_now, _ = collect_due(db, datetime(2026, 10, 2, 9, 0))
        failed = record_result(
            db, run_now[0], error="검색 API 한도 초과", now=datetime(2026, 10, 2, 9, 0)
        )
        assert failed.last_status == STATUS_FAILED and "한도 초과" in failed.last_result

        # 늦게 실행하면 결과에도 그 사실이 남는다
        run_now, _ = collect_due(db, datetime(2026, 10, 3, 10, 0))
        late_done = record_result(db, run_now[0], text="결과", now=datetime(2026, 10, 3, 10, 0))
        assert "늦게 실행" in late_done.last_result

        # 꺼진 루틴은 후보에 없다
        update_routine(db, news.id, enabled=False)
        assert collect_due(db, datetime(2026, 10, 4, 9, 0)) == ([], [])
        update_routine(db, news.id, enabled=True)

        # 한 틱 상한
        for i in range(4):
            create_routine(db, name=f"기타{i}", task="뭔가", time_of_day="09:00", now=base)
        run_now, _ = collect_due(db, datetime(2026, 9, 29, 9, 0), limit=2)
        assert len(run_now) == 2

        # once 는 한 번 돌면 다음이 없다
        one = create_routine(
            db, name="한 번만", task="한 번만 해줘", kind="once",
            at="2026-10-05T07:00:00", now=base,
        )
        assert one.next_run_at == "2026-10-05T07:00:00"
        run_now, _ = collect_due(db, datetime(2026, 10, 5, 7, 0), limit=9)
        target = [d for d in run_now if d.routine.id == one.id]
        assert target
        after_once = record_result(db, target[0], text="끝", now=datetime(2026, 10, 5, 7, 0))
        assert after_once.next_run_at == ""
        assert get_routine(db, one.id).run_count == 1

        # 실행 요청문
        msgs = build_run_messages(news)
        assert msgs[0]["role"] == "system" and msgs[1]["content"] == "뉴스 3개 정리해줘"
        assert "되묻지 말고" in msgs[0]["content"]
        assert "아침 뉴스" in msgs[0]["content"]
        assert "웹 검색" not in msgs[0]["content"]  # 도구가 있으면 굳이 말하지 않는다

        no_tools = build_run_messages(news, tools_available=False)[0]["content"]
        assert "웹 검색" in no_tools
        assert "쓸 수 없다" in no_tools
        assert "실시간 정보를 가져올 수 없습니다" not in no_tools
        assert "계산·번역·요약·글쓰기" in no_tools
        with_ev = build_run_messages(news, evidence="# History 발췌\n지난주 뉴스")
        assert "지난주 뉴스" in with_ev[0]["content"]

        # 전달 문구
        on_time = check_due("2026-10-01T09:00:00", datetime(2026, 10, 1, 9, 0))
        assert format_delivery(news, "본문", on_time) == "**아침 뉴스**\n\n본문"
        tardy = check_due("2026-10-01T09:00:00", datetime(2026, 10, 1, 9, 40))
        assert "40분 늦게" in format_delivery(news, "본문", tardy)
        assert "결과 없음" in format_delivery(news, "   ", on_time)

        assert notify_summary(news, "한 줄  결과") == "한 줄 결과"
        assert notify_summary(news, "가" * 200).endswith("…")
        assert len(notify_summary(news, "가" * 200)) == 120
        assert notify_summary(news, "") == "결과 없음"
        db.close()

    print("routine_runner self-check ok")
