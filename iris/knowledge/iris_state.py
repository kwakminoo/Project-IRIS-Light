"""Iris Wiki `IRIS` 칸 — 아이리스가 지금 어떤 상태인지, 무엇을 하기로 했는지.

    user/IRIS/
      index.md              ← 지금 설정 한 장 + 다른 노트로 가는 링크
      routines/<slug>.md    ← 사용자가 시킨 반복 작업 하나당 한 장 (정의 + 실행 이력)

**비밀값은 절대 쓰지 않는다.** 위키는 그냥 마크다운 파일이라 적는 순간 평문으로
남는다. API 키·토큰은 "설정됨/없음" 여부만 적는다 — 무엇이 빠졌는지 진단하는 데는
그걸로 충분하고, 유출 위험은 없다.

설정이 바뀌면 `diff_state` 로 무엇이 달라졌는지 뽑아 History에도 한 줄 남긴다.
그래야 "저번에 뭘 바꿨더라"를 나중에 검색할 수 있다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from iris.knowledge.iris_wiki import IrisWiki, slugify_note_name
from iris.storage.routines import Routine, deliver_labels

IRIS_DIR = "IRIS"
ROUTINE_DIR = f"{IRIS_DIR}/routines"

# index.md 에 이 순서로 나온다. 값이 비면 그 줄은 건너뛴다.
STATE_ORDER: tuple[str, ...] = (
    "대화 모델",
    "백엔드",
    "Iris Agent 게이트웨이",
    "Iris Agent API 키",
    "등록된 API",
    "History 기록",
    "History 검색",
    "모델 자동 전환",
    "전환 후보",
    "선제 전환",
)

# 노출되면 안 되는 값 — 이름에 이런 게 들어가면 bool 로만 적는다.
_SECRET_HINTS = ("key", "token", "secret", "password", "비밀", "키")


def is_secret_label(label: str) -> bool:
    low = str(label or "").lower()
    return any(hint in low for hint in _SECRET_HINTS)


def mask(value: Any) -> str:
    """비밀값 → 설정 여부만."""
    return "설정됨" if str(value or "").strip() else "없음"


def build_state(
    *,
    ollama_model: str = "",
    hermes_enabled: bool = False,
    agent_base_url: str = "",
    hermes_api_key: str = "",
    api_providers: list[Any] | None = None,
    history: Any = None,
    failover: Any = None,
    embed_model: str = "",
) -> dict[str, str]:
    """지금 상태를 라벨→문구로. 비밀값은 여기서 이미 가려진다."""
    state: dict[str, str] = {}
    state["대화 모델"] = str(ollama_model or "").strip() or "(선택 안 됨)"
    state["백엔드"] = "Iris Agent" if hermes_enabled else "Ollama 직행"
    if hermes_enabled:
        state["Iris Agent 게이트웨이"] = str(agent_base_url or "").strip()
        state["Iris Agent API 키"] = mask(hermes_api_key)

    providers = list(api_providers or [])
    if providers:
        bits = []
        for p in providers:
            name = str(getattr(p, "name", "") or "?")
            has_key = mask(getattr(p, "api_key", ""))
            enabled = getattr(p, "enabled", True)
            mark = "" if enabled else " (꺼짐)"
            bits.append(f"{name}(키 {has_key}){mark}")
        state["등록된 API"] = ", ".join(bits)

    if history is not None:
        if not getattr(history, "enabled", True):
            state["History 기록"] = "꺼짐"
        else:
            kinds = [
                label
                for flag, label in (
                    ("record_chat", "대화"),
                    ("record_actions", "수행"),
                    ("record_artifacts", "생성물"),
                    ("record_inputs", "입력"),
                )
                if getattr(history, flag, False)
            ]
            state["History 기록"] = ", ".join(kinds) if kinds else "없음"
            if embed_model:
                state["History 검색"] = f"키워드 + 의미 (`{embed_model}`)"
            else:
                state["History 검색"] = "키워드만 (임베딩 모델 없음)"

    if failover is not None:
        if not getattr(failover, "enabled", False):
            state["모델 자동 전환"] = "꺼짐"
        else:
            mode = {
                "model-chain": "다른 모델로 전환",
                "retry": "같은 모델로 재시도",
                "off": "전환 안 함",
            }.get(str(getattr(failover, "mode", "")), str(getattr(failover, "mode", "")))
            state["모델 자동 전환"] = mode
            chain = list(getattr(failover, "chain", []) or [])
            if chain:
                state["전환 후보"] = " → ".join(
                    f"{getattr(e, 'model', '?')}[{getattr(e, 'backend', '?')}]" for e in chain
                )
            else:
                state["전환 후보"] = "없음 (설정에서 추가하세요)"
            if getattr(failover, "preempt_enabled", False):
                pct = getattr(failover, "preempt_percent", 0)
                state["선제 전환"] = f"사용률 {int(pct)}% 넘으면 미리 전환"

    # 어떤 경로로 들어왔든 비밀 라벨은 값이 남지 않게 한 번 더 막는다.
    for label in list(state):
        if is_secret_label(label) and state[label] not in ("설정됨", "없음"):
            state[label] = mask(state[label])
    return state


def diff_state(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """바뀐 항목만 사람이 읽을 문장으로."""
    lines: list[str] = []
    for label in [*after, *(k for k in before if k not in after)]:
        old = (before or {}).get(label)
        new = (after or {}).get(label)
        if old == new:
            continue
        if old is None:
            lines.append(f"{label}: (없음) → {new}")
        elif new is None:
            lines.append(f"{label}: {old} → (없음)")
        else:
            lines.append(f"{label}: {old} → {new}")
    return lines


def render_index(
    state: dict[str, str],
    routines: list[Routine] | None = None,
    *,
    updated_at: str = "",
) -> str:
    stamp = updated_at or datetime.now().isoformat(timespec="seconds")
    lines = [
        "# IRIS",
        "",
        "> 아이리스가 지금 어떤 설정으로 돌고 있는지, 그리고 사용자가 시켜 둔",
        "> 반복 작업이 무엇인지 모아 둔 칸입니다. 이 PC에만 있습니다.",
        "> API 키·토큰은 **설정 여부만** 적습니다 — 값은 여기 남지 않습니다.",
        "",
        "## 지금 상태",
        "",
    ]
    ordered = [k for k in STATE_ORDER if k in state]
    ordered += [k for k in state if k not in STATE_ORDER]
    if not ordered:
        lines.append("_아직 상태 정보 없음_")
    for label in ordered:
        lines.append(f"- **{label}** — {state[label]}")
    lines.append("")

    lines.append("## 시켜 둔 일 (루틴)")
    lines.append("")
    items = list(routines or [])
    if not items:
        lines.append("_아직 없음 — 아이리스에게 \"매일 9시에 뉴스 3개 정리해줘\" 처럼 말해보세요._")
    else:
        on = sum(1 for r in items if r.enabled)
        lines.append(f"**{len(items)}개 (켜짐 {on}개)**")
        lines.append("")
        for r in items:
            mark = "x" if r.enabled else " "
            # [[대상|표시]] — 링크는 슬러그로, 눈에는 사람이 붙인 이름으로.
            link = f"[[{slugify_note_name(r.name)}|{r.name}]]"
            lines.append(f"- [{mark}] {link} — {r.schedule.describe()} · {deliver_labels(r.deliver)}")
            detail = []
            if r.next_run_at:
                detail.append(f"다음 {r.next_run_at}")
            if r.last_run_at:
                detail.append(f"최근 {r.last_run_at} ({r.last_status})")
            if r.miss_count:
                detail.append(f"놓침 {r.miss_count}회")
            if detail:
                lines.append(f"  - {' · '.join(detail)}")
    lines.append("")

    lines.append("## 더 자세한 곳")
    lines.append("")
    lines.append("- 사용자 프로필: `user/profile/profile.md`")
    lines.append("- 등록된 스킬: `user/integrations/skills.md`")
    lines.append("- 등록된 MCP: `user/integrations/mcp.md`")
    lines.append("- 학습한 업무: `user/learning/workflows.md`")
    lines.append("- 대화·수행 기록: `user/history/index.md`")
    lines.append("")
    lines.append(f"> updated: {stamp}")
    lines.append("")
    return "\n".join(lines)


def render_routine_note(routine: Routine, runs: list[dict[str, str]] | None = None) -> str:
    """루틴 한 장 — 무엇을 시켰고, 언제 돌았고, 뭐가 나왔는지."""
    lines = [
        f"# {routine.name}",
        "",
        "> 사용자가 아이리스에게 시켜 둔 반복 작업입니다.",
        "> 설정에서 끄거나 \"그 루틴 지워줘\" 라고 말하면 사라집니다.",
        "",
        "## 시킨 내용",
        "",
        routine.task,
        "",
        "## 언제 · 어떻게",
        "",
        f"- 주기: {routine.schedule.describe()}",
        f"- 전달: {deliver_labels(routine.deliver)}",
        f"- 상태: {'켜짐' if routine.enabled else '꺼짐'}",
    ]
    if routine.next_run_at:
        lines.append(f"- 다음 실행: {routine.next_run_at}")
    if routine.source:
        lines.append(f"- 등록 경로: {routine.source}")
    if routine.created_at:
        lines.append(f"- 만든 날: {routine.created_at}")
    lines.append("")

    lines.append("## 실행 이력")
    lines.append("")
    lines.append(f"- 실행 {routine.run_count}회 · 놓침 {routine.miss_count}회")
    if routine.last_run_at:
        lines.append(f"- 마지막 실행: {routine.last_run_at} ({routine.last_status})")
    lines.append("")

    items = list(runs or [])
    if not items:
        if routine.last_result:
            lines.append("### 최근 결과")
            lines.append("")
            lines.append(routine.last_result)
            lines.append("")
        else:
            lines.append("_아직 실행된 적 없음_")
            lines.append("")
    else:
        for run in items[:20]:
            when = str(run.get("at") or "")
            status = str(run.get("status") or "")
            lines.append(f"### {when} · {status}")
            lines.append("")
            body = str(run.get("result") or "").strip()
            lines.append(body or "_(결과 없음)_")
            lines.append("")

    lines.append(f"> updated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    return "\n".join(lines)


def routine_rel_path(routine: Routine) -> str:
    return f"{ROUTINE_DIR}/{slugify_note_name(routine.name)}.md"


def sync_iris_index(
    wiki: IrisWiki,
    state: dict[str, str],
    routines: list[Routine] | None = None,
) -> None:
    wiki.write_user_note(f"{IRIS_DIR}/index.md", render_index(state, routines))


def sync_routine_note(
    wiki: IrisWiki,
    routine: Routine,
    runs: list[dict[str, str]] | None = None,
) -> str:
    rel = routine_rel_path(routine)
    wiki.write_user_note(rel, render_routine_note(routine, runs))
    return rel


def remove_routine_note(wiki: IrisWiki, routine: Routine) -> bool:
    path = (wiki.user_root / routine_rel_path(routine)).resolve()
    root = wiki.user_root.resolve()
    if root not in path.parents or not path.is_file():
        return False
    path.unlink()
    return True


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from iris.storage.database import Database
    from iris.storage.routines import create_routine, mark_ran

    assert is_secret_label("Iris Agent API 키") is True
    assert is_secret_label("access token") is True
    assert is_secret_label("대화 모델") is False
    assert mask("sk-real-secret") == "설정됨" and mask("") == "없음"

    class _H:
        enabled = True
        record_chat = True
        record_actions = True
        record_artifacts = False
        record_inputs = True

    class _F:
        enabled = True
        mode = "model-chain"
        preempt_enabled = True
        preempt_percent = 95.0
        chain = [type("E", (), {"model": "free:a", "backend": "ollama"})()]

    class _P:
        name = "OpenRouter"
        api_key = "sk-super-secret-value"
        enabled = True

    state = build_state(
        ollama_model="qwen3:8b",
        hermes_enabled=True,
        agent_base_url="http://127.0.0.1:8642/v1",
        hermes_api_key="sk-hermes-secret",
        api_providers=[_P()],
        history=_H(),
        failover=_F(),
        embed_model="bge-m3",
    )
    blob = "\n".join(f"{k}={v}" for k, v in state.items())
    # 비밀값이 어떤 형태로도 새면 안 된다
    assert "sk-hermes-secret" not in blob
    assert "sk-super-secret-value" not in blob
    assert state["Iris Agent API 키"] == "설정됨"
    assert "키 설정됨" in state["등록된 API"]
    assert state["대화 모델"] == "qwen3:8b"
    assert state["백엔드"] == "Iris Agent"
    assert "대화, 수행, 입력" == state["History 기록"]
    assert "bge-m3" in state["History 검색"]
    assert "free:a[ollama]" in state["전환 후보"]
    assert "95%" in state["선제 전환"]

    off = build_state(ollama_model="m", history=type("X", (), {"enabled": False})())
    assert off["History 기록"] == "꺼짐" and "History 검색" not in off
    assert build_state()["대화 모델"] == "(선택 안 됨)"

    changes = diff_state(state, {**state, "대화 모델": "gemma4:free"})
    assert changes == ["대화 모델: qwen3:8b → gemma4:free"]
    assert diff_state(state, state) == []
    added = diff_state({}, {"새 항목": "값"})
    assert added == ["새 항목: (없음) → 값"]
    removed = diff_state({"옛 항목": "값"}, {})
    assert removed == ["옛 항목: 값 → (없음)"]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = Database(root / "s.db")
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")

        r = create_routine(
            db,
            name="아침 뉴스 브리핑",
            task="오늘 주요 뉴스 3개를 골라 한 줄씩 정리해줘",
            time_of_day="09:00",
            now=datetime(2026, 9, 29, 8, 0),
        )

        sync_iris_index(wiki, state, [r])
        index = (wiki.user_root / IRIS_DIR / "index.md").read_text(encoding="utf-8")
        assert "# IRIS" in index
        assert "qwen3:8b" in index
        assert "sk-hermes-secret" not in index
        assert "아침 뉴스 브리핑" in index  # 슬러그가 아니라 읽을 이름이 보여야 한다
        assert "[[아침-뉴스-브리핑|아침 뉴스 브리핑]]" in index
        assert "매일 09:00" in index
        assert "[x]" in index  # 켜져 있다

        empty = render_index({}, [])
        assert "아직 상태 정보 없음" in empty and "아직 없음" in empty

        rel = sync_routine_note(wiki, r)
        note = (wiki.user_root / rel).read_text(encoding="utf-8")
        assert "오늘 주요 뉴스 3개" in note
        assert "매일 09:00" in note
        assert "채팅 · 알림" in note
        assert "아직 실행된 적 없음" in note

        ran = mark_ran(db, r.id, status="ok", result="1. 뉴스A\n2. 뉴스B\n3. 뉴스C")
        sync_routine_note(
            wiki, ran, [{"at": "2026-09-29T09:00:00", "status": "ok", "result": "1. 뉴스A"}]
        )
        note2 = (wiki.user_root / rel).read_text(encoding="utf-8")
        assert "실행 1회" in note2 and "1. 뉴스A" in note2

        off_routine = create_routine(db, name="꺼진 것", task="뭔가", now=datetime(2026, 9, 29, 8, 0))
        from iris.storage.routines import update_routine

        off_routine = update_routine(db, off_routine.id, enabled=False)
        sync_iris_index(wiki, state, [r, off_routine])
        index2 = (wiki.user_root / IRIS_DIR / "index.md").read_text(encoding="utf-8")
        assert "[ ] " in index2 and "켜짐 1개" in index2

        assert remove_routine_note(wiki, r) is True
        assert remove_routine_note(wiki, r) is False
        db.close()

    print("iris_state self-check ok")
