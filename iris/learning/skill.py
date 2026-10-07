"""녹화 이벤트 → 다시 실행할 수 있는 단계 목록(스킬).

사람이 실제로 한 녹화에는 군더더기가 많다 — 작업 표시줄 클릭, 창 끌기, 지웠다
다시 친 글자, 끝난 뒤 스크롤, 녹화를 끄러 돌아간 창. 여기서 그것들을 걸러
"앱 띄우기 → 클릭 → 입력 → 키" 단계로 정리한다. 모델은 쓰지 않는다
(각 클릭이 무엇인지는 local_learner 가 화면을 보고 채운다).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from iris.learning.models import LearningEvent

SKILL_VERSION = 1
_DOUBLE_CLICK_SEC = 0.45
_DOUBLE_CLICK_PX = 6.0
_SAME_SPOT_PX = 48.0
_SHELL_PROCESSES = {"explorer.exe", "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe"}


@dataclass
class SkillParam:
    name: str  # 영문 식별자 (message, recipient)
    label: str  # 사용자에게 보이는 이름 (보낼 메시지)
    example: str  # 녹화 때 실제로 쓴 값


@dataclass
class SkillStep:
    kind: str  # activate_app | click | type | hotkey | scroll
    process: str = ""
    title: str = ""
    exe: str = ""
    # click
    x: float = 0.0
    y: float = 0.0
    button: str = "left"
    double: bool = False
    shot: str = ""  # 녹화 화면 (세션 폴더 기준)
    target: str = ""  # 누른 요소 설명 — 실행 때 화면에서 이걸 찾는다. {param} 가능
    visible_text: str = ""
    win_rect: list[int] = field(default_factory=list)  # 녹화 때 누른 창 (left, top, right, bottom)
    # type
    text: str = ""  # {param} 가능
    clear_first: bool = False
    # hotkey
    keys: str = ""
    # scroll
    dy: int = 0
    timestamp: float = 0.0


@dataclass
class Skill:
    skill_id: str
    name: str = ""
    description: str = ""
    params: list[SkillParam] = field(default_factory=list)
    steps: list[SkillStep] = field(default_factory=list)
    screen_width: int = 0
    screen_height: int = 0
    session_dir: str = ""
    version: int = SKILL_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Skill":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        steps = [SkillStep(**s) for s in data.get("steps") or []]
        params = [SkillParam(**p) for p in data.get("params") or []]
        return cls(
            skill_id=str(data.get("skill_id") or ""),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            params=params,
            steps=steps,
            screen_width=int(data.get("screen_width") or 0),
            screen_height=int(data.get("screen_height") or 0),
            session_dir=str(data.get("session_dir") or ""),
            version=int(data.get("version") or SKILL_VERSION),
        )


def is_skill_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and "steps" in data and "skill_id" in data


# ----------------------------------------------------------------------
# 파라미터 치환
# ----------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def fill(template: str, values: dict[str, str]) -> str:
    """'{message}' → 실제 값. 모르는 이름은 그대로 둔다."""
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), template or "")


def placeholders(template: str) -> list[str]:
    return _PLACEHOLDER.findall(template or "")


def apply_params(skill: Skill, params: list[SkillParam]) -> None:
    """녹화 때 쓴 값(example)이 들어간 자리를 {name} 으로 바꾼다.

    이미 다른 이름으로 바꿔 둔 자리({text} → {message})도 새 이름으로 옮긴다."""
    old_names = {p.example: p.name for p in skill.params}
    for p in params:
        prev = old_names.get(p.example)
        if prev and prev != p.name:
            for s in skill.steps:
                for attr in ("text", "target", "visible_text"):
                    setattr(s, attr, getattr(s, attr).replace("{" + prev + "}", "{" + p.name + "}"))
    kept = {p.example for p in params}
    for example, name in old_names.items():
        if example not in kept:
            # 칸에서 뺀 값은 녹화 때 글자 그대로 되돌린다
            for s in skill.steps:
                for attr in ("text", "target", "visible_text"):
                    setattr(s, attr, getattr(s, attr).replace("{" + name + "}", example))
    skill.params = params
    for p in sorted(params, key=lambda p: -len(p.example)):
        ex = (p.example or "").strip()
        if not ex:
            continue
        token = "{" + p.name + "}"
        for s in skill.steps:
            if s.kind == "type" and ex in s.text:
                s.text = s.text.replace(ex, token)
            if s.kind == "click":
                if ex in s.target:
                    s.target = s.target.replace(ex, token)
                if ex in s.visible_text:
                    s.visible_text = s.visible_text.replace(ex, token)


# ----------------------------------------------------------------------
# 이벤트 → 단계
# ----------------------------------------------------------------------


_SHELL_CLASSES = {"shell_traywnd", "shell_secondarytraywnd", "progman", "workerw"}


def _is_shell(process: str, title: str) -> bool:
    return process.lower() in _SHELL_PROCESSES and not title.strip()


def _clicked_shell(e: LearningEvent) -> bool:
    """작업 표시줄·바탕화면 클릭. 그 순간 포커스가 다른 앱이어도 누른 곳으로 판단한다."""
    under = e.metadata.get("under") or {}
    if str(under.get("class") or "").lower() in _SHELL_CLASSES:
        return True
    return _is_shell(e.process_name, e.window_title)


def build_steps(events: Iterable[LearningEvent]) -> list[SkillStep]:
    evs = sorted(
        (e for e in events if not e.exclude_from_trace), key=lambda e: e.timestamp
    )
    start_process = ""
    for e in evs:
        if e.event_type == "context":
            start_process = e.process_name
            break

    steps: list[SkillStep] = []
    fg_process = start_process
    last_activated = start_process

    def activate(e: LearningEvent) -> None:
        nonlocal last_activated
        if not e.process_name or _is_shell(e.process_name, e.window_title):
            return
        if e.process_name == last_activated:
            return
        last_activated = e.process_name
        steps.append(
            SkillStep(
                kind="activate_app",
                process=e.process_name,
                title=e.window_title,
                exe=str(e.metadata.get("exe") or ""),
                timestamp=e.timestamp,
            )
        )

    for e in evs:
        et = e.event_type
        if et == "window_change":
            fg_process = e.process_name
            activate(e)
            continue
        if et in {"click", "double_click", "right_click"}:
            if _clicked_shell(e):
                # 작업 표시줄·바탕화면 — 앱을 띄우려는 클릭. 실행할 땐 activate_app 이 대신한다
                continue
            activate(e)
            button = "right" if et == "right_click" else "left"
            prev = steps[-1] if steps else None
            if (
                button == "left"
                and prev is not None
                and prev.kind == "click"
                and not prev.double
                and e.timestamp - prev.timestamp <= _DOUBLE_CLICK_SEC
                and abs((e.x or 0) - prev.x) <= _DOUBLE_CLICK_PX
                and abs((e.y or 0) - prev.y) <= _DOUBLE_CLICK_PX
            ):
                prev.double = True
                continue
            steps.append(
                SkillStep(
                    kind="click",
                    process=e.process_name,
                    title=e.window_title,
                    x=float(e.x or 0),
                    y=float(e.y or 0),
                    button=button,
                    double=et == "double_click",
                    shot=str(e.metadata.get("shot") or ""),
                    win_rect=_rect_of(e),
                    timestamp=e.timestamp,
                )
            )
            continue
        if et == "type_text":
            if not (e.text or "").strip() or e.text == "[REDACTED]":
                continue
            activate(e)
            field_text = str(e.metadata.get("field_text") or "").strip()
            if field_text and field_text != e.text:
                _collapse_typing(steps, e.process_name)
                steps.append(
                    SkillStep(kind="type", process=e.process_name, title=e.window_title,
                              text=field_text, clear_first=True, timestamp=e.timestamp)
                )
            else:
                prev = steps[-1] if steps else None
                # 입력창을 누르고 바로 친 글자 — 실행할 땐 남아 있던 글자를 지우고 넣는다
                # (안 지우면 전에 쳐 둔 글자까지 같이 보내진다, 실제 사례)
                clear = prev is not None and prev.kind == "click" and prev.process == e.process_name
                steps.append(
                    SkillStep(kind="type", process=e.process_name, title=e.window_title,
                              text=e.text or "", clear_first=clear, timestamp=e.timestamp)
                )
            continue
        if et == "hotkey":
            activate(e)
            steps.append(
                SkillStep(kind="hotkey", process=e.process_name, title=e.window_title,
                          keys=e.key or "", timestamp=e.timestamp)
            )
            continue
        if et == "scroll":
            dy = int(e.metadata.get("dy") or 0)
            prev = steps[-1] if steps else None
            if prev is not None and prev.kind == "scroll" and prev.process == e.process_name:
                prev.dy += dy
                continue
            steps.append(
                SkillStep(kind="scroll", process=e.process_name, title=e.window_title,
                          x=float(e.x or 0), y=float(e.y or 0), dy=dy, timestamp=e.timestamp)
            )
            continue
        # drag 는 대부분 창 옮기기라 v1 에서는 건너뛴다

    _ = fg_process
    return _trim(_drop_repeat_clicks(steps), start_process)


def _rect_of(e: LearningEvent) -> list[int]:
    rect = (e.metadata.get("under") or {}).get("rect") or []
    try:
        r = [int(v) for v in rect]
    except (TypeError, ValueError):
        return []
    return r if len(r) == 4 and r[2] > r[0] and r[3] > r[1] else []


def _collapse_typing(steps: list[SkillStep], process: str) -> None:
    """입력창 전체 글자를 아는 입력이 왔다 — 같은 창에서 그 전에 친 글자·지우기는 뺀다."""
    i = len(steps) - 1
    while i >= 0:
        s = steps[i]
        if s.process != process or s.kind == "activate_app":
            break
        if s.kind == "hotkey" and s.keys not in {"backspace", "delete"}:
            break
        if s.kind == "type" or (s.kind == "hotkey" and s.keys in {"backspace", "delete"}):
            del steps[i]
        i -= 1


def _drop_repeat_clicks(steps: list[SkillStep]) -> list[SkillStep]:
    """같은 곳을 한 번 더 누른 클릭 (입력창 다시 클릭 등) — 실행할 땐 한 번이면 된다.

    지웠다 다시 친 글자를 합친(_collapse_typing) 뒤에야 두 클릭이 나란히 붙으므로
    단계를 다 만든 다음에 거른다."""
    out: list[SkillStep] = []
    for s in steps:
        prev = out[-1] if out else None
        if (
            s.kind == "click"
            and not s.double
            and prev is not None
            and prev.kind == "click"
            and prev.button == s.button
            and prev.process == s.process
            and prev.title == s.title
            and abs(s.x - prev.x) <= _SAME_SPOT_PX
            and abs(s.y - prev.y) <= _SAME_SPOT_PX
        ):
            continue
        out.append(s)
    return out


_NO_APP = {"", "system idle process", "system"}


def _trim(steps: list[SkillStep], start_process: str) -> list[SkillStep]:
    # 포커스가 비어 있던 순간의 클릭 (어느 앱인지 모름) — 다시 할 수 없다
    steps = [s for s in steps if s.kind not in {"activate_app", "click"} or s.process.lower() not in _NO_APP]
    # 녹화를 끄러 처음 창(터미널·IRIS)으로 돌아간 뒤의 단계
    if start_process:
        cut = len(steps)
        for i in range(len(steps) - 1, -1, -1):
            if steps[i].process == start_process:
                cut = i
            else:
                break
        has_other = any(s.process != start_process for s in steps[:cut])
        if has_other:
            steps = steps[:cut]
    # 끝난 뒤 둘러보는 스크롤
    while steps and steps[-1].kind == "scroll":
        steps.pop()
    # 학습 버튼을 누르러 IRIS(처음 창)에 있던 동안의 스크롤·클릭도 업무가 아니다
    if start_process and any(s.process != start_process for s in steps):
        while steps and steps[0].process == start_process:
            steps.pop(0)
    return steps
