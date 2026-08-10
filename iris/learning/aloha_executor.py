"""Aloha Actor/Executor bridge — IRIS 프로세스와 Qt 바인딩 분리."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Protocol

from iris.learning.models import WorkflowRun
from iris.learning.paths import aloha_act_root, traces_dir
from iris.learning.workflow_registry import LearnedWorkflowRepository

log = logging.getLogger("iris.learning.executor")


class ExecutorProtocol(Protocol):
    def execute(
        self, *, trace_id: str, task: str, workflow_id: int = 0
    ) -> WorkflowRun: ...

    def get_status(self, run_id: str) -> WorkflowRun | None: ...

    def shutdown(self) -> None: ...


def _no_window_kwargs() -> dict:
    from iris.system.win_subprocess import no_window_kwargs

    return no_window_kwargs()


class AlohaBridge:
    """Aloha_Act client/server lifecycle (hidden console)."""

    def __init__(
        self,
        *,
        client_url: str = "http://127.0.0.1:7888",
        server_url: str = "http://127.0.0.1:7887",
    ) -> None:
        self.client_url = client_url.rstrip("/")
        self.server_url = server_url.rstrip("/")
        self._server: subprocess.Popen | None = None
        self._client: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def ensure_running(self) -> None:
        with self._lock:
            if self._ping(f"{self.client_url}/"):
                return
            act = aloha_act_root()
            py = sys.executable
            env = os.environ.copy()
            # 별도 runtime이 있으면 우선
            from iris.learning.aloha_runtime import runtime_python, runtime_status

            runtime = runtime_python()
            if runtime.is_file():
                st = runtime_status()
                if st.get("ok"):
                    py = str(runtime)
                else:
                    log.warning("aloha runtime present but unhealthy: %s", st.get("detail"))
            else:
                # 사용자 override
                override = Path.home() / ".iris-light" / "runtimes" / "aloha" / "python.exe"
                if override.is_file():
                    py = str(override)
            kw = _no_window_kwargs()
            if self._server is None or self._server.poll() is not None:
                self._server = subprocess.Popen(
                    [py, str(act / "app_server.py")],
                    cwd=str(act),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kw,
                )
            if self._client is None or self._client.poll() is not None:
                self._client = subprocess.Popen(
                    [py, str(act / "app_client.py")],
                    cwd=str(act),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kw,
                )
            for _ in range(40):
                if self._ping(f"{self.client_url}/"):
                    return
                time.sleep(0.25)
            raise RuntimeError("Aloha client failed to start")

    def _ping(self, url: str) -> bool:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            return False

    def run_task(self, *, task: str, trace_id: str, max_steps: int = 40) -> dict:
        self.ensure_running()
        body = json.dumps(
            {
                "task": task,
                "trace_id": trace_id,
                "selected_screen": 0,
                "max_steps": max_steps,
                "server_url": self.server_url,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.client_url}/run_task",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise RuntimeError(f"Aloha run_task HTTP {exc.code}: {detail}") from exc

    def shutdown(self) -> None:
        with self._lock:
            for proc in (self._client, self._server):
                if proc is None:
                    continue
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            self._client = None
            self._server = None


class AlohaExecutor:
    def __init__(
        self,
        registry: LearnedWorkflowRepository,
        bridge: AlohaBridge | None = None,
    ) -> None:
        self._registry = registry
        self._bridge = bridge or AlohaBridge()
        self._runs: dict[str, WorkflowRun] = {}

    def execute(
        self, *, trace_id: str, task: str, workflow_id: int = 0
    ) -> WorkflowRun:
        run_id = uuid.uuid4().hex
        # ensure trace in Aloha_Act/trace_data
        src = traces_dir() / f"{trace_id}.json"
        dst = aloha_act_root() / "trace_data" / f"{trace_id}.json"
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
        run = WorkflowRun(
            run_id=run_id,
            workflow_id=workflow_id,
            trace_id=trace_id,
            task=task,
            status="running",
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._runs[run_id] = run
        self._registry.save_run(
            run_id=run_id,
            workflow_id=workflow_id,
            trace_id=trace_id,
            task=task,
            status="running",
            started_at=run.started_at,
        )
        try:
            result = self._bridge.run_task(task=task, trace_id=trace_id)
            run.status = "succeeded"
            run.message = json.dumps(result, ensure_ascii=False)[:500]
            if workflow_id:
                self._registry.mark_run(workflow_id)
        except Exception as exc:
            log.exception("workflow execute failed")
            run.status = "failed"
            run.message = str(exc)[:500]
        run.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._registry.save_run(
            run_id=run_id,
            workflow_id=workflow_id,
            trace_id=trace_id,
            task=task,
            status=run.status,
            message=run.message,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )
        return run

    def get_status(self, run_id: str) -> WorkflowRun | None:
        if run_id in self._runs:
            return self._runs[run_id]
        row = self._registry.get_run(run_id)
        if not row:
            return None
        return WorkflowRun(
            run_id=str(row["run_id"]),
            workflow_id=int(row["workflow_id"]),
            trace_id=str(row["trace_id"]),
            task=str(row["task"]),
            status=str(row["status"]),
            message=str(row.get("message") or ""),
            started_at=str(row.get("started_at") or ""),
            finished_at=str(row.get("finished_at") or ""),
        )

    def shutdown(self) -> None:
        self._bridge.shutdown()


class MockExecutor:
    def __init__(self, registry: LearnedWorkflowRepository) -> None:
        self._registry = registry
        self._runs: dict[str, WorkflowRun] = {}

    def execute(
        self, *, trace_id: str, task: str, workflow_id: int = 0
    ) -> WorkflowRun:
        run_id = uuid.uuid4().hex
        run = WorkflowRun(
            run_id=run_id,
            workflow_id=workflow_id,
            trace_id=trace_id,
            task=task,
            status="succeeded",
            message="mock ok",
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._runs[run_id] = run
        self._registry.save_run(
            run_id=run_id,
            workflow_id=workflow_id,
            trace_id=trace_id,
            task=task,
            status=run.status,
            message=run.message,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )
        if workflow_id:
            self._registry.mark_run(workflow_id)
        return run

    def get_status(self, run_id: str) -> WorkflowRun | None:
        return self._runs.get(run_id)

    def shutdown(self) -> None:
        return None
