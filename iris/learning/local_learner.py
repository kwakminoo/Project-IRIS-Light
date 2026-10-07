"""로컬 비전 모델로 녹화를 스킬로 만든다 — 클라우드 API 없이.

예전 Ollama 경로는 영상 가운데 프레임 한 장과 앞쪽 이벤트 24개만 보냈다. 여기서는
클릭마다 그 순간 화면(녹화기가 저장한 click_XXXX.jpg)을 보여 주고 "무엇을
눌렀는지"를 적게 한다. 실행할 때는 그 설명으로 화면에서 같은 요소를 다시 찾는다.
입력한 글자는 바꿔 넣을 수 있는 칸(파라미터)으로 만든다.
"""

from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path
from typing import Callable

from iris.infrastructure.local_vision import vision_chat
from iris.learning.models import LearningEvent, SemanticTrace, SessionManifest, TraceStep
from iris.learning.skill import Skill, SkillParam, SkillStep, apply_params, build_steps

log = logging.getLogger("iris.learning.local_learner")

_CROP = 800  # 클릭 주변 (원본 픽셀) — 작게 자르면 3B 모델이 요소를 못 알아본다
_SEND_SIDE = 560  # 모델에 보낼 때 크기

# 3B 모델은 "빨간 원 위치"를 물으면 원 자체를 답하고, 한국어 예시를 주면 예시를 그대로
# 베낀다. 마우스 포인터를 그려 넣고 영어로 물으면 실제 요소를 답한다 (카톡 녹화로 확인).
_DESCRIBE_PROMPT = (
    "This is a screenshot of a Windows app ({app}). The mouse pointer is about to click "
    "something. What UI element is directly under the tip of the mouse pointer? Answer in "
    "one short Korean phrase, then the exact text written on that element. "
    "Format: 요소: ... / 글자: ..."
)

_SUMMARY_PROMPT = """사용자가 컴퓨터로 한 업무를 단계로 정리했습니다.

{steps}

이 업무를 다시 시킬 때 쓸 스킬로 정리하세요. 입력한 글자 중 다음번에 바뀔 만한 것
(받는 사람, 메시지 내용, 검색어 등)은 파라미터로 만드세요. 고정된 것은 파라미터로 만들지 마세요.

JSON 형식만 출력:
{{"name": "짧은 한국어 스킬 이름",
  "description": "무엇을 하는 스킬인지 한국어 한 문장",
  "params": [{{"name": "영문 소문자 식별자", "label": "한국어 이름", "example": "녹화에서 실제로 입력한 글자 그대로"}}]}}"""


def _extract_json(text: str) -> dict | None:
    raw = (text or "").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _draw_pointer(img, x: float, y: float) -> None:
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    pts = [(x, y), (x, y + 34), (x + 9, y + 26), (x + 16, y + 40), (x + 22, y + 37),
           (x + 15, y + 23), (x + 26, y + 23)]
    d.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))


def click_image(shot_path: Path, x: float, y: float) -> bytes | None:
    """클릭 주변을 잘라 마우스 포인터를 그려 넣은 PNG."""
    try:
        from PIL import Image
    except ImportError:
        return None
    if not shot_path.is_file():
        return None
    img = Image.open(shot_path).convert("RGB")
    w, h = img.size
    half = _CROP // 2
    left = int(min(max(0, x - half), max(0, w - _CROP)))
    top = int(min(max(0, y - half), max(0, h - _CROP)))
    crop = img.crop((left, top, min(w, left + _CROP), min(h, top + _CROP))).copy()
    _draw_pointer(crop, x - left, y - top)
    # 800px 그대로 보내는 것보다 560px 이 빠르고 답이 더 안정적이었다 (카톡 녹화로 비교)
    scale = _SEND_SIDE / float(max(crop.size))
    if scale < 1.0:
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)))
    return _png(crop)


def parse_description(text: str) -> tuple[str, str]:
    """'요소: 메시지 입력 / 글자: 메시지 입력' → (요소, 글자)."""
    raw = " ".join((text or "").split()).strip().strip("`")
    target = visible = ""
    m = re.search(r"요소\s*[:：]\s*(.+?)(?:/\s*글자|$)", raw)
    if m:
        target = m.group(1).strip(" /")
    m = re.search(r"글자\s*[:：]\s*(.+)$", raw)
    if m:
        visible = m.group(1).strip(" /")
    if not target and raw and len(raw) <= 60:
        target = raw
    return target[:120], visible[:120]


def describe_steps_text(steps: list[SkillStep]) -> str:
    lines = []
    for i, s in enumerate(steps, 1):
        if s.kind == "activate_app":
            lines.append(f"{i}. {s.process} 창 띄우기")
        elif s.kind == "click":
            how = "더블클릭" if s.double else ("우클릭" if s.button == "right" else "클릭")
            lines.append(f"{i}. {s.target or '(알 수 없는 요소)'} {how}")
        elif s.kind == "type":
            lines.append(f"{i}. 입력: \"{s.text}\"")
        elif s.kind == "hotkey":
            lines.append(f"{i}. 키: {s.keys}")
        elif s.kind == "scroll":
            lines.append(f"{i}. 스크롤 {'위로' if s.dy > 0 else '아래로'}")
    return "\n".join(lines)


class LocalSkillLearner:
    """LearnerProtocol 구현 — manager 가 learn() 을 부른다."""

    def __init__(
        self,
        ollama_base_url: str,
        model: str | Callable[[], str | None],
        *,
        on_progress: Callable[[str], None] | None = None,
        timeout_sec: float = 180.0,
    ) -> None:
        self._base_url = ollama_base_url
        self._model = model
        self._model_name = ""
        self._on_progress = on_progress
        self._timeout = timeout_sec

    def _progress(self, msg: str) -> None:
        log.info(msg)
        if self._on_progress:
            try:
                self._on_progress(msg)
            except Exception:
                pass

    def _client(self):
        from iris.infrastructure.ollama_client import OllamaClient

        return OllamaClient(self._base_url)

    def learn(
        self,
        session_dir: Path,
        manifest: SessionManifest,
        events: list[LearningEvent],
    ) -> SemanticTrace:
        skill = self.build_skill(session_dir, manifest, events)
        path = session_dir / "skill.json"
        skill.save(path)
        trace = SemanticTrace(
            trace_id=skill.skill_id,
            steps=[
                TraceStep(step_idx=i, action=f"{s.kind}: {s.target or s.text or s.keys or s.process}")
                for i, s in enumerate(skill.steps)
            ],
            path=str(path),
            raw={"name": skill.name, "summary": skill.description},
        )
        manifest.status = "ready" if skill.steps else "failed"
        return trace

    def _resolve_model(self) -> str:
        """녹화를 시작할 땐 모델이 없다가 그 사이에 받아질 수 있어 학습 시점에 고른다."""
        m = self._model() if callable(self._model) else self._model
        return (m or "").strip()

    def build_skill(
        self, session_dir: Path, manifest: SessionManifest, events: list[LearningEvent]
    ) -> Skill:
        steps = build_steps(events)
        model = self._resolve_model()
        skill = Skill(
            skill_id=f"skill_{manifest.session_id[:12]}",
            steps=steps,
            screen_width=manifest.screen_width,
            screen_height=manifest.screen_height,
            session_dir=str(session_dir),
        )
        if not model:
            # 화면을 보는 모델이 없으면 클릭 설명 없이 — 실행은 녹화 그림 맞추기로 한다
            self._progress("업무 학습: 화면 분석 모델이 없어 클릭 설명 없이 저장해요")
            apps = [s.process.removesuffix(".exe") for s in steps if s.kind == "activate_app"]
            skill.name = f"{apps[0] if apps else '화면'} 업무"
            typed = [s.text for s in steps if s.kind == "type" and s.text.strip()]
            if len(typed) == 1:
                apply_params(skill, [SkillParam(name="text", label="입력할 내용", example=typed[0])])
            return skill
        self._model_name = model
        client = self._client()
        clicks = [s for s in steps if s.kind == "click"]
        for n, s in enumerate(clicks, 1):
            self._progress(f"업무 학습: 클릭 {n}/{len(clicks)} 화면 보는 중")
            self._describe_click(client, session_dir, s)
        self._progress("업무 학습: 스킬 이름과 바꿔 넣을 칸 정리 중")
        self._summarize(client, skill)
        return skill

    def _describe_click(self, client, session_dir: Path, step: SkillStep) -> None:
        img = click_image(session_dir / step.shot, step.x, step.y) if step.shot else None
        if img is None:
            return
        try:
            text = vision_chat(
                client,
                self._model_name,
                _DESCRIBE_PROMPT.format(app=step.process or "?"),
                [img],
                timeout_sec=self._timeout,
            )
        except Exception as e:
            log.warning("click describe failed: %s", e)
            return
        step.target, step.visible_text = parse_description(text)

    def _summarize(self, client, skill: Skill) -> None:
        typed = [s.text for s in skill.steps if s.kind == "type" and s.text.strip()]
        try:
            text = vision_chat(
                client,
                self._model_name,
                _SUMMARY_PROMPT.format(steps=describe_steps_text(skill.steps)),
                [],
                system="Answer with JSON only.",
                timeout_sec=self._timeout,
            )
            obj = _extract_json(text) or {}
        except Exception as e:
            log.warning("skill summary failed: %s", e)
            obj = {}
        skill.name = str(obj.get("name") or "").strip()[:60]
        skill.description = str(obj.get("description") or "").strip()[:200]
        params: list[SkillParam] = []
        seen: set[str] = set()
        for p in obj.get("params") or []:
            if not isinstance(p, dict):
                continue
            name = re.sub(r"[^a-z0-9_]", "_", str(p.get("name") or "").strip().lower()).strip("_")
            example = str(p.get("example") or "").strip()
            # 모델이 지어낸 예시는 버린다 — 실제로 입력한 글자 안에 있어야 한다
            if not name or name in seen or not example or not any(example in t for t in typed):
                continue
            seen.add(name)
            params.append(SkillParam(name=name, label=str(p.get("label") or name)[:30], example=example))
        if not params and len(typed) == 1:
            # 입력이 하나뿐이면 그것이 바꿔 넣을 내용이다 (메시지 보내기 류)
            params.append(SkillParam(name="text", label="입력할 내용", example=typed[0]))
        apply_params(skill, params)
        if not skill.name:
            apps = [s.process.removesuffix(".exe") for s in skill.steps if s.kind == "activate_app"]
            skill.name = f"{apps[0] if apps else '화면'} 업무"
