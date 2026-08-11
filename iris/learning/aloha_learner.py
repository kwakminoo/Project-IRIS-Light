"""ShowUI-Aloha Learner 파이프라인 어댑터 — UI와 강결합 금지."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Protocol

from iris.learning.models import LearningEvent, SemanticTrace, SessionManifest, TraceStep
from iris.learning.paths import aloha_act_root, aloha_learn_root, traces_dir

log = logging.getLogger("iris.learning.learner")


class LearnerProtocol(Protocol):
    def learn(
        self,
        session_dir: Path,
        manifest: SessionManifest,
        events: list[LearningEvent],
    ) -> SemanticTrace: ...


def _load_vlm_keys() -> dict[str, str]:
    """소스 하드코딩 금지 — env + Hermes .env."""
    keys: dict[str, str] = {}
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "IRIS_OPENAI_API_KEY", "IRIS_ANTHROPIC_API_KEY"):
        val = os.environ.get(name, "").strip()
        if val:
            keys[name] = val
    hermes_env = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"
    if hermes_env.is_file():
        try:
            for line in hermes_env.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"} and v and k not in keys:
                    keys[k] = v
        except Exception:
            pass
    return keys


def _events_to_structural_trace(
    events: list[LearningEvent], trace_id: str
) -> SemanticTrace:
    """API 없을 때 structural semantic skeleton (pending_vlm)."""
    steps: list[TraceStep] = []
    usable = [e for e in events if not e.exclude_from_trace]
    # 의미 단위로 묶기: click/drag/type/scroll/window
    idx = 0
    i = 0
    while i < len(usable):
        e = usable[i]
        if e.event_type in {"context"}:
            i += 1
            continue
        idx += 1
        app = e.process_name or e.window_title or "app"
        if e.event_type == "window_change":
            steps.append(
                TraceStep(
                    step_idx=idx,
                    observation=f"Foreground changed to {app}",
                    think="Track application context",
                    action=f"Focus {app}",
                    expectation="Target app is active",
                )
            )
        elif e.event_type in {"click", "press", "double_click", "right_click"}:
            steps.append(
                TraceStep(
                    step_idx=idx,
                    observation=f"UI in {app}",
                    think="Interact with on-screen control",
                    action=f"Click at ({int(e.x or 0)}, {int(e.y or 0)})",
                    expectation="UI responds to click",
                )
            )
        elif e.event_type == "drag":
            steps.append(
                TraceStep(
                    step_idx=idx,
                    observation=f"Drag gesture in {app}",
                    think="Move or select content",
                    action="Drag pointer",
                    expectation="Drag completes",
                )
            )
        elif e.event_type == "scroll":
            steps.append(
                TraceStep(
                    step_idx=idx,
                    observation=f"Scrollable content in {app}",
                    think="Reveal more content",
                    action="Scroll",
                    expectation="Viewport updates",
                )
            )
        elif e.event_type == "key_down":
            # coalesce typing burst
            keys = []
            j = i
            while j < len(usable) and usable[j].event_type in {"key_down", "key_up"}:
                if usable[j].event_type == "key_down" and usable[j].key:
                    keys.append(usable[j].key or "")
                j += 1
            i = j - 1
            shown = "".join(k for k in keys if len(k) == 1)[:40]
            action = f"Type '{shown}'" if shown else f"Press {keys[0] if keys else 'key'}"
            steps.append(
                TraceStep(
                    step_idx=idx,
                    observation=f"Text input in {app}",
                    think="Enter text or shortcut",
                    action=action,
                    expectation="Input accepted",
                )
            )
        i += 1
        if len(steps) >= 40:
            break

    if not steps:
        steps.append(
            TraceStep(
                step_idx=1,
                observation="Session recorded",
                think="No discrete UI actions detected",
                action="No-op",
                expectation="Review raw session",
            )
        )

    raw = {
        "trajectory": [
            {
                "step_idx": s.step_idx,
                "caption": {
                    "observation": s.observation,
                    "think": s.think,
                    "action": s.action,
                    "expectation": s.expectation,
                },
            }
            for s in steps
        ]
    }
    return SemanticTrace(trace_id=trace_id, steps=steps, raw=raw)


def load_trace_file(path: Path, trace_id: str) -> SemanticTrace:
    data = json.loads(path.read_text(encoding="utf-8"))
    steps: list[TraceStep] = []
    for item in data.get("trajectory") or []:
        cap = item.get("caption") or {}
        # field hard-code 최소화 — 소문자/Pascal 둘 다
        def g(*names: str) -> str:
            for n in names:
                if n in cap and cap[n]:
                    return str(cap[n])
            return ""

        steps.append(
            TraceStep(
                step_idx=int(item.get("step_idx") or len(steps) + 1),
                observation=g("observation", "Observation"),
                think=g("think", "Think", "reasoning"),
                action=g("action", "Action"),
                expectation=g("expectation", "Expectation"),
                raw=item,
            )
        )
    return SemanticTrace(trace_id=trace_id, steps=steps, path=str(path), raw=data)


class AlohaLearner:
    """upstream Aloha_Learn 파이프라인 또는 Ollama/structural fallback."""

    def __init__(
        self,
        *,
        api_provider: str | None = None,
        openai_model: str | None = None,
        claude_model: str | None = None,
        ollama_model: str | None = None,
        ollama_base_url: str | None = None,
        prefer_upstream: bool = True,
        force_structural: bool = False,
    ) -> None:
        self.api_provider = (
            api_provider
            or os.environ.get("IRIS_ALOHA_VLM_PROVIDER", "").strip()
            or "auto"
        )
        self.openai_model = (
            openai_model
            or os.environ.get("IRIS_ALOHA_OPENAI_MODEL", "").strip()
            or "gpt-4o"
        )
        self.claude_model = (
            claude_model
            or os.environ.get("IRIS_ALOHA_CLAUDE_MODEL", "").strip()
            or "claude-sonnet-4-20250514"
        )
        self.ollama_model = (ollama_model or "").strip()
        self.ollama_base_url = (
            ollama_base_url
            or os.environ.get("IRIS_OLLAMA_BASE_URL", "").strip()
            or "http://127.0.0.1:11434/v1"
        )
        self.prefer_upstream = prefer_upstream
        self.force_structural = force_structural

    def configure(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        ollama_base_url: str | None = None,
        force_structural: bool | None = None,
    ) -> None:
        if provider is not None:
            self.api_provider = provider
        if model:
            p = (self.api_provider or "").lower()
            if p == "ollama":
                self.ollama_model = model
            elif p in {"anthropic", "claude"}:
                self.claude_model = model
            else:
                self.openai_model = model
        if ollama_base_url:
            self.ollama_base_url = ollama_base_url
        if force_structural is not None:
            self.force_structural = force_structural

    def learn(
        self,
        session_dir: Path,
        manifest: SessionManifest,
        events: list[LearningEvent],
    ) -> SemanticTrace:
        trace_id = f"iris_{session_dir.name}"
        if self.force_structural:
            return self._save_structural(session_dir, manifest, events, trace_id, pending=True)

        provider = (self.api_provider or "auto").lower()
        keys = _load_vlm_keys()
        has_openai = bool(keys.get("OPENAI_API_KEY") or keys.get("IRIS_OPENAI_API_KEY"))
        has_anthropic = bool(
            keys.get("ANTHROPIC_API_KEY") or keys.get("IRIS_ANTHROPIC_API_KEY")
        )

        if provider == "auto":
            if self.ollama_model:
                provider = "ollama"
            elif has_openai:
                provider = "openai"
            elif has_anthropic:
                provider = "anthropic"
            else:
                provider = "ollama" if self.ollama_model else "none"

        if provider == "ollama" and self.ollama_model:
            try:
                return self._run_ollama(session_dir, manifest, events, trace_id)
            except Exception as exc:
                log.warning("ollama VLM learn failed: %s", exc)

        if provider in {"openai", "anthropic", "claude"} and self.prefer_upstream:
            if (provider == "openai" and has_openai) or (
                provider in {"anthropic", "claude"} and has_anthropic
            ):
                try:
                    return self._run_upstream(session_dir, trace_id, keys, provider=provider)
                except Exception as exc:
                    log.warning("upstream Aloha learn failed: %s", exc)

        pending = not (has_openai or has_anthropic or bool(self.ollama_model))
        return self._save_structural(
            session_dir, manifest, events, trace_id, pending=pending
        )

    def _save_structural(
        self,
        session_dir: Path,
        manifest: SessionManifest,
        events: list[LearningEvent],
        trace_id: str,
        *,
        pending: bool,
    ) -> SemanticTrace:
        trace = _events_to_structural_trace(events, trace_id)
        out = traces_dir() / f"{trace_id}.json"
        out.write_text(json.dumps(trace.raw, ensure_ascii=False, indent=2), encoding="utf-8")
        act_trace = aloha_act_root() / "trace_data" / f"{trace_id}.json"
        try:
            act_trace.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, act_trace)
        except Exception:
            pass
        shutil.copy2(out, session_dir / "trace.json")
        trace.path = str(out)
        if pending:
            manifest.status = "pending_vlm"
            manifest.error = "VLM unavailable — structural trace saved"
        else:
            manifest.status = "ready"
        return trace

    def _run_ollama(
        self,
        session_dir: Path,
        manifest: SessionManifest,
        events: list[LearningEvent],
        trace_id: str,
    ) -> SemanticTrace:
        """Ollama OpenAI-compatible / native chat with optional frame."""
        import base64
        import urllib.request

        base = self.ollama_base_url.rstrip("/")
        if base.endswith("/v1"):
            native = base[:-3]
        else:
            native = base

        # 대표 프레임 1장 (있으면)
        img_b64 = ""
        video = session_dir / "inputs" / "recording.mp4"
        if video.is_file():
            try:
                import cv2

                cap = cv2.VideoCapture(str(video))
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                mid = max(0, total // 2)
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
                ok, frame = cap.read()
                cap.release()
                if ok and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    img_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            except Exception:
                img_b64 = ""

        steps_hint = []
        for e in events:
            if e.exclude_from_trace:
                continue
            if e.event_type in {"click", "drag", "scroll", "key_down", "window_change"}:
                steps_hint.append(
                    f"{e.event_type} @({e.x},{e.y}) key={e.key} app={e.process_name}"
                )
            if len(steps_hint) >= 24:
                break

        prompt = (
            "You generate Aloha-style GUI learning traces. "
            "Return ONLY JSON: {\"trajectory\":[{\"step_idx\":1,\"caption\":"
            "{\"observation\":\"\",\"think\":\"\",\"action\":\"\",\"expectation\":\"\"}}]}. "
            "Summarize the user demonstration into 3-12 semantic steps.\n"
            f"Events:\n" + "\n".join(steps_hint)
        )
        content: list[dict] = [{"type": "text", "text": prompt}]
        if img_b64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                }
            )
        body = {
            "model": self.ollama_model,
            "messages": [{"role": "user", "content": content if img_b64 else prompt}],
            "stream": False,
            "format": "json",
        }
        req = urllib.request.Request(
            f"{native}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = (data.get("message") or {}).get("content") or ""
        parsed = {}
        try:
            parsed = json.loads(msg)
        except json.JSONDecodeError:
            import re

            m = re.search(r"\{.*\}", msg, re.S)
            if m:
                parsed = json.loads(m.group(0))
        if not parsed.get("trajectory"):
            raise RuntimeError("ollama returned no trajectory")

        out = traces_dir() / f"{trace_id}.json"
        out.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        act_trace = aloha_act_root() / "trace_data" / f"{trace_id}.json"
        act_trace.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, act_trace)
        shutil.copy2(out, session_dir / "trace.json")
        manifest.status = "ready"
        return load_trace_file(out, trace_id)

    def _run_upstream(
        self,
        session_dir: Path,
        trace_id: str,
        keys: dict[str, str],
        *,
        provider: str = "openai",
    ) -> SemanticTrace:
        learn_root = aloha_learn_root()
        if not (learn_root / "parser.py").is_file():
            raise FileNotFoundError("Aloha_Learn not vendored")

        cfg_dir = learn_root / "config"
        cfg_dir.mkdir(exist_ok=True)
        api_path = cfg_dir / "api_keys.json"
        payload = {
            "OPENAI_API_KEY": keys.get("OPENAI_API_KEY")
            or keys.get("IRIS_OPENAI_API_KEY")
            or "",
            "CLAUDE_API_KEY": keys.get("ANTHROPIC_API_KEY")
            or keys.get("IRIS_ANTHROPIC_API_KEY")
            or "",
            "openai": keys.get("OPENAI_API_KEY") or keys.get("IRIS_OPENAI_API_KEY") or "",
            "claude": keys.get("ANTHROPIC_API_KEY") or keys.get("IRIS_ANTHROPIC_API_KEY") or "",
            "anthropic": keys.get("ANTHROPIC_API_KEY")
            or keys.get("IRIS_ANTHROPIC_API_KEY")
            or "",
        }
        api_path.write_text(json.dumps(payload), encoding="utf-8")

        env = os.environ.copy()
        if payload["OPENAI_API_KEY"]:
            env["OPENAI_API_KEY"] = payload["OPENAI_API_KEY"]
        if payload["CLAUDE_API_KEY"]:
            env["ANTHROPIC_API_KEY"] = payload["CLAUDE_API_KEY"]
        env["IRIS_ALOHA_VLM_PROVIDER"] = (
            "claude" if provider in {"anthropic", "claude"} else "openai"
        )
        env["IRIS_ALOHA_OPENAI_MODEL"] = self.openai_model
        env["IRIS_ALOHA_CLAUDE_MODEL"] = self.claude_model

        import subprocess

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        proc = subprocess.run(
            [sys.executable, str(learn_root / "parser.py"), str(session_dir)],
            cwd=str(learn_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=creationflags,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "parser failed")[:500])

        candidates = list(session_dir.glob("*_trace.json")) + [session_dir / "trace.json"]
        trace_path = next((p for p in candidates if p.is_file()), None)
        if trace_path is None:
            raise FileNotFoundError("trace json not produced")

        final = traces_dir() / f"{trace_id}.json"
        shutil.copy2(trace_path, final)
        act_trace = aloha_act_root() / "trace_data" / f"{trace_id}.json"
        act_trace.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(final, act_trace)
        shutil.copy2(final, session_dir / "trace.json")
        return load_trace_file(final, trace_id)


class MockLearner:
    """테스트용 — API 호출 없음."""

    def learn(
        self,
        session_dir: Path,
        manifest: SessionManifest,
        events: list[LearningEvent],
    ) -> SemanticTrace:
        trace_id = f"mock_{session_dir.name}"
        trace = _events_to_structural_trace(events, trace_id)
        out = session_dir / "trace.json"
        out.write_text(json.dumps(trace.raw, ensure_ascii=False, indent=2), encoding="utf-8")
        traces_dir().mkdir(parents=True, exist_ok=True)
        dest = traces_dir() / f"{trace_id}.json"
        shutil.copy2(out, dest)
        trace.path = str(dest)
        manifest.status = "ready"
        return trace
