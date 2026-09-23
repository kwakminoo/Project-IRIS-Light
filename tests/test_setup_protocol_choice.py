"""시작 프로토콜 — needs_user choice 상태머신 + fake runner 시퀀스."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from iris.system.setup_protocol import (
    CORE_STEP_IDS,
    SetupProtocol,
    SetupStepResult,
    VISIBLE_CONSOLE_STEPS,
    core_needs_user_next,
    normalize_user_choice,
    redact_secrets,
)


class ChoiceStateMachineTests(TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize_user_choice("ABORT"), "abort")
        self.assertEqual(normalize_user_choice("later"), "skip")
        self.assertEqual(normalize_user_choice(None), "done")
        self.assertEqual(normalize_user_choice("  "), "done")

    def test_transition_table(self) -> None:
        cases = [
            ("abort", False, "abort"),
            ("install", False, "install"),
            ("done", False, "reverify"),
            ("skip", False, "reverify"),
            ("skip", True, "skip"),
            ("later", True, "skip"),
        ]
        for choice, allow_skip, expected in cases:
            with self.subTest(choice=choice, allow_skip=allow_skip):
                self.assertEqual(
                    core_needs_user_next(choice, allow_skip=allow_skip), expected
                )


class VisibleConsoleContractTests(TestCase):
    def test_shared_constant(self) -> None:
        self.assertEqual(
            VISIBLE_CONSOLE_STEPS,
            frozenset({"ollama_install", "hermes_install", "emulator"}),
        )


class FakeRunnerChoiceSequenceTests(TestCase):
    """install → needs_user → choice 시퀀스를 mock runner로 고정."""

    def test_install_then_done_advances(self) -> None:
        calls: list[str] = []

        def on_user(result: SetupStepResult) -> str:
            calls.append(f"user:{result.step_id}:{result.status}")
            if result.status == "needs_user" and result.can_install:
                return "install"
            return "done"

        progress: list[str] = []

        def on_progress(result: SetupStepResult) -> None:
            progress.append(f"{result.step_id}:{result.status}")

        proto = SetupProtocol(simulate=False, dry_run=False, allow_core_skip=False)

        # 첫 호출 needs_user, install 후 done — 나머지 단계는 즉시 done
        step_hits: dict[str, int] = {s: 0 for s in CORE_STEP_IDS}

        def _fake_runner(step_id: str):
            def _run() -> SetupStepResult:
                step_hits[step_id] += 1
                if step_id == "ollama_install" and step_hits[step_id] == 1:
                    return SetupStepResult(
                        step_id=step_id,
                        status="needs_user",
                        message="install me",
                        can_install=True,
                        label="Ollama",
                    )
                return SetupStepResult(step_id=step_id, status="done", message="ok")

            return _run

        runners = [(sid, _fake_runner(sid)) for sid in CORE_STEP_IDS]

        def _dispatch(step_id: str) -> SetupStepResult:
            calls.append(f"install:{step_id}")
            return SetupStepResult(step_id=step_id, status="done", message="installed")

        with (
            patch.object(proto, "_core_runners", return_value=runners),
            patch.object(proto, "_dispatch_install", side_effect=_dispatch),
            patch.object(proto, "_save_state"),
        ):
            ok = proto.run_core(on_progress=on_progress, on_user=on_user)

        self.assertTrue(ok)
        self.assertIn("install:ollama_install", calls)
        self.assertTrue(any(p.startswith("ollama_install:needs_user") for p in progress))
        self.assertTrue(proto._state.get("core_ready"))

    def test_repair_skip_marks_skipped(self) -> None:
        def on_user(result: SetupStepResult) -> str:
            return "skip"

        proto = SetupProtocol(simulate=False, dry_run=False, allow_core_skip=True)
        step_hits = {"ollama_install": 0}

        def _ollama() -> SetupStepResult:
            step_hits["ollama_install"] += 1
            if step_hits["ollama_install"] == 1:
                return SetupStepResult(
                    step_id="ollama_install",
                    status="needs_user",
                    message="need",
                    can_install=False,  # 자동 install 회피 → on_user skip
                )
            return SetupStepResult(step_id="ollama_install", status="done", message="ok")

        runners: list = []
        for sid in CORE_STEP_IDS:
            if sid == "ollama_install":
                runners.append((sid, _ollama))
            else:
                runners.append(
                    (
                        sid,
                        lambda s=sid: SetupStepResult(
                            step_id=s, status="done", message="ok"
                        ),
                    )
                )

        with (
            patch.object(proto, "_core_runners", return_value=runners),
            patch.object(proto, "_save_state"),
        ):
            ok = proto.run_core(on_user=on_user)

        self.assertTrue(ok)
        st = proto._state.get("steps", {}).get("ollama_install", {})
        self.assertEqual(st.get("status"), "skipped")

    def test_abort_stops(self) -> None:
        def on_user(_result: SetupStepResult) -> str:
            return "abort"

        proto = SetupProtocol(simulate=False, dry_run=False)

        def _needs() -> SetupStepResult:
            return SetupStepResult(
                step_id="state_init",
                status="needs_user",
                message="x",
                can_install=False,
            )

        runners = [("state_init", _needs)]
        with (
            patch.object(proto, "_core_runners", return_value=runners),
            patch.object(proto, "_save_state"),
        ):
            ok = proto.run_core(on_user=on_user)
        self.assertFalse(ok)


class RedactGatewayTests(TestCase):
    def test_redact_idempotent_for_worker_gate(self) -> None:
        raw = "API_SERVER_KEY=abcDEF123456789"
        once = redact_secrets(raw)
        self.assertNotIn("abcDEF123456789", once)
        self.assertEqual(redact_secrets(once), once)
