"""LearningManager — UI는 여기만 호출."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from iris.learning.aloha_adapter import write_aloha_input
from iris.learning.aloha_executor import AlohaExecutor, ExecutorProtocol
from iris.learning.aloha_learner import AlohaLearner, LearnerProtocol
from iris.learning.models import LearningState, LearnedWorkflow, WorkflowRun
from iris.learning.naming import generate_workflow_name
from iris.learning.permission import PermissionPolicy, policy_for
from iris.learning.recorder import DemonstrationRecorder
from iris.learning.workflow_registry import LearnedWorkflowRepository
from iris.storage.database import Database
from iris.storage.learning_prefs import LearningPreferences, load_learning_preferences

log = logging.getLogger("iris.learning.manager")


class LearningManager:
    def __init__(
        self,
        db: Database,
        *,
        learner: LearnerProtocol | None = None,
        executor: ExecutorProtocol | None = None,
        on_state: Callable[[LearningState], None] | None = None,
        on_activity: Callable[[str], None] | None = None,
        iris_hwnd_provider: Callable[[], list[int]] | None = None,
        learning_prefs: LearningPreferences | None = None,
    ) -> None:
        self._db = db
        self._registry = LearnedWorkflowRepository(db)
        self._learner: LearnerProtocol = learner or AlohaLearner()
        self._executor: ExecutorProtocol = executor or AlohaExecutor(self._registry)
        self._on_state = on_state
        self._on_activity = on_activity
        self._iris_hwnd_provider = iris_hwnd_provider
        self._prefs = learning_prefs or load_learning_preferences(db)
        self.state = LearningState.IDLE
        self._recorder: DemonstrationRecorder | None = None
        self._session_id: str = ""
        self._last_error: str = ""
        self._record_only = False

    @property
    def registry(self) -> LearnedWorkflowRepository:
        return self._registry

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def session_id(self) -> str:
        return self._session_id

    def _set_state(self, state: LearningState) -> None:
        self.state = state
        if self._on_state:
            self._on_state(state)

    def _activity(self, line: str) -> None:
        if self._on_activity:
            self._on_activity(line)

    def set_learning_prefs(self, prefs: LearningPreferences) -> None:
        self._prefs = prefs

    def set_learner(self, learner: LearnerProtocol) -> None:
        self._learner = learner

    def permission_policy(self) -> PermissionPolicy:
        return policy_for(self._prefs.permission_level)

    def set_record_only(self, value: bool) -> None:
        self._record_only = value
        configure = getattr(self._learner, "configure", None)
        if callable(configure):
            configure(force_structural=value)

    def start_recording(self) -> str:
        if self.state != LearningState.IDLE:
            raise RuntimeError(f"cannot start from {self.state}")
        self._session_id = uuid.uuid4().hex
        hwnds = self._iris_hwnd_provider() if self._iris_hwnd_provider else []
        pol = self.permission_policy()
        self._recorder = DemonstrationRecorder(
            self._session_id,
            fps=4.0,
            iris_hwnds=hwnds,
            on_error=lambda m: log.warning("recorder: %s", m),
            record_keyboard=pol.record_keyboard,
            store_key_chars=pol.store_key_chars,
        )
        self._recorder.start()
        self._set_state(LearningState.RECORDING)
        self._activity(f"업무 학습 시작 ({pol.label_ko})")
        return self._session_id

    def stop_hooks_immediately(self) -> None:
        if self._recorder is not None:
            self._recorder.stop_hooks_first()

    def finalize_and_process_payload(self) -> dict[str, Any]:
        """UI 스레드 밖 worker에서 호출 — Learner + Registry."""
        if self._recorder is None:
            raise RuntimeError("no active recorder")
        manifest = self._recorder.finalize(status="processing")
        events = self._recorder.events_snapshot()
        session_path = self._recorder.directory
        write_aloha_input(session_path, manifest, events)
        # manifest 다시 저장
        (session_path / "manifest.json").write_text(
            __import__("json").dumps(asdict(manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        try:
            trace = self._learner.learn(session_path, manifest, events)
        except Exception as exc:
            log.exception("learn failed")
            manifest.status = "failed"
            manifest.error = str(exc)[:400]
            (session_path / "manifest.json").write_text(
                __import__("json").dumps(asdict(manifest), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            raise

        name, summary = generate_workflow_name(events, trace)
        apps = Counter(
            e.process_name
            for e in events
            if not e.exclude_from_trace and e.process_name
        )
        primary = ", ".join(a for a, _ in apps.most_common(3))
        status = manifest.status if manifest.status in {"ready", "pending_vlm"} else "ready"
        wf = self._registry.upsert(
            trace_id=trace.trace_id,
            name=name,
            summary=summary,
            status=status,
            source_session_id=self._session_id,
            trace_path=trace.path or str(session_path / "trace.json"),
            primary_apps=primary,
        )
        manifest.trace_path = wf.trace_path
        if status != "pending_vlm":
            manifest.status = "ready"
        (session_path / "manifest.json").write_text(
            __import__("json").dumps(asdict(manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "workflow_id": wf.id,
            "trace_id": wf.trace_id,
            "name": wf.name,
            "summary": wf.summary,
            "status": wf.status,
            "session_id": self._session_id,
            "trace_path": wf.trace_path,
        }

    def mark_processing(self) -> None:
        self._set_state(LearningState.PROCESSING)
        self._activity("업무 학습 정리 중…")

    def mark_success(self, result: dict[str, Any]) -> None:
        name = result.get("name") or "학습된 업무"
        self._activity(f"업무 학습 완료 · {name}")
        self._recorder = None
        self._set_state(LearningState.IDLE)

    def mark_error(self, err: str) -> None:
        self._last_error = err
        log.error("learning error: %s", err)
        self._activity(f"업무 학습 오류: {err[:120]}")
        self._set_state(LearningState.ERROR)

    def recover_to_idle(self) -> None:
        self._recorder = None
        self._set_state(LearningState.IDLE)

    def interrupt_on_shutdown(self) -> None:
        try:
            if self.state == LearningState.RECORDING and self._recorder is not None:
                self._recorder.interrupt()
                self._recorder = None
            if hasattr(self._executor, "shutdown"):
                self._executor.shutdown()
        except Exception:
            log.exception("shutdown learning cleanup")
        self.state = LearningState.IDLE

    # --- Hermes / MCP API ---
    def list_learned_workflows(self, *, enabled_only: bool = False) -> list[LearnedWorkflow]:
        return self._registry.list(enabled_only=enabled_only)

    def get_learned_workflow(self, workflow_id: int) -> LearnedWorkflow | None:
        return self._registry.get(workflow_id)

    def execute_workflow(self, trace_id: str, task: str = "") -> WorkflowRun:
        wf = self._registry.get_by_trace_id(trace_id)
        workflow_id = wf.id if wf else 0
        task_text = task or (wf.name if wf else trace_id)
        return self._executor.execute(
            trace_id=trace_id, task=task_text, workflow_id=workflow_id
        )

    def run_learned_workflow(self, workflow_id: int, task: str = "") -> WorkflowRun:
        wf = self._registry.get(workflow_id)
        if wf is None:
            raise KeyError(f"workflow {workflow_id} not found")
        return self.execute_workflow(wf.trace_id, task or wf.name)

    def get_workflow_run_status(self, run_id: str) -> WorkflowRun | None:
        return self._executor.get_status(run_id)

    def session_directory(self) -> Path | None:
        if self._recorder is None:
            return None
        return self._recorder.directory
