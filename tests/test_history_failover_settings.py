"""History 설정과 AI Hub 모델 전환 설정의 저장·복원 계약."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication, QListWidgetItem

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
_APP = QApplication.instance() or QApplication(sys.argv)

from iris.runtime.model_failover import MODE_OFF, MODE_RETRY  # noqa: E402
from iris.storage.database import Database  # noqa: E402
from iris.storage.failover_prefs import (  # noqa: E402
    FallbackEntry,
    load_failover_settings,
    load_history_settings,
)
from iris.ui.settings.history_failover_box import (  # noqa: E402
    build_history_failover_box,
    save_history_failover,
)
from iris.ui.ai_hub.routing_panel import AiRoutingPanel  # noqa: E402


def _add_entry(box, model: str, backend: str = "ollama", free: bool = True) -> None:
    entry = FallbackEntry(model=model, backend=backend, free=free)
    item = QListWidgetItem(model)
    item.setData(256, entry)
    box._chain_list.addItem(item)


class HistoryFailoverBoxTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "s.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_defaults_are_shown(self) -> None:
        box = build_history_failover_box(self.db)
        self.assertTrue(box.history_enabled.isChecked())
        self.assertTrue(box.record_chat.isChecked())
        self.assertTrue(box.record_inputs.isChecked())
        panel = AiRoutingPanel(self.db)
        self.assertTrue(panel._enabled.isChecked())
        self.assertEqual(panel._chain_list.count(), 0)

    def test_round_trip_through_the_database(self) -> None:
        box = build_history_failover_box(self.db)
        box.record_actions.setChecked(False)
        box.retrieval_limit.setValue(9)
        box.embed_model.setText("bge-m3")
        panel = AiRoutingPanel(self.db)
        panel._mode.setCurrentIndex(panel._mode.findData(MODE_RETRY))
        panel._retry_count.setValue(4)
        panel._preempt_percent.setValue(88)
        panel._ask_summary.setChecked(False)
        _add_entry(panel, "free:a")
        _add_entry(panel, "free:b", backend="api", free=False)

        save_history_failover(self.db, box)
        panel.persist()

        history = load_history_settings(self.db)
        self.assertFalse(history.record_actions)
        self.assertTrue(history.record_chat)
        self.assertEqual(history.retrieval_limit, 9)
        self.assertEqual(history.embed_model, "bge-m3")

        failover = load_failover_settings(self.db)
        self.assertEqual(failover.mode, MODE_RETRY)
        self.assertEqual(failover.retry_count, 4)
        self.assertEqual(failover.preempt_percent, 88.0)
        self.assertFalse(failover.ask_old_model_summary)
        self.assertEqual(
            [(e.model, e.backend, e.free) for e in failover.chain],
            [("free:a", "ollama", True), ("free:b", "api", False)],
        )

        # 다시 열면 저장한 값이 그대로 보여야 한다
        reopened = build_history_failover_box(self.db)
        self.assertFalse(reopened.record_actions.isChecked())
        self.assertEqual(reopened.retrieval_limit.value(), 9)
        reopened_panel = AiRoutingPanel(self.db)
        self.assertEqual(reopened_panel._chain_list.count(), 2)
        self.assertEqual(
            [e.model for e in reopened_panel._chain_entries()], ["free:a", "free:b"]
        )

    def test_turning_history_off_disables_its_controls(self) -> None:
        box = build_history_failover_box(self.db)
        box.history_enabled.setChecked(False)
        self.assertFalse(box.record_chat.isEnabled())
        self.assertFalse(box.retrieval_limit.isEnabled())
        self.assertFalse(box.embed_model.isEnabled())

        box.history_enabled.setChecked(True)
        self.assertTrue(box.record_chat.isEnabled())

    def test_embed_model_follows_the_semantic_search_toggle(self) -> None:
        box = build_history_failover_box(self.db)
        box.embed_enabled.setChecked(False)
        self.assertFalse(box.embed_model.isEnabled())
        box.embed_enabled.setChecked(True)
        self.assertTrue(box.embed_model.isEnabled())

    def test_retry_count_only_matters_in_retry_mode(self) -> None:
        panel = AiRoutingPanel(self.db)
        panel._mode.setCurrentIndex(panel._mode.findData(MODE_RETRY))
        self.assertTrue(panel._retry_count.isEnabled())
        panel._mode.setCurrentIndex(panel._mode.findData(MODE_OFF))
        self.assertFalse(panel._retry_count.isEnabled())

    def test_turning_failover_off_disables_the_chain_editor(self) -> None:
        panel = AiRoutingPanel(self.db)
        panel._enabled.setChecked(False)
        self.assertFalse(panel._chain_list.isEnabled())
        self.assertFalse(panel._mode.isEnabled())

    def test_preempt_percent_follows_its_toggle(self) -> None:
        panel = AiRoutingPanel(self.db)
        panel._preempt_enabled.setChecked(False)
        self.assertFalse(panel._preempt_percent.isEnabled())
        panel._preempt_enabled.setChecked(True)
        self.assertTrue(panel._preempt_percent.isEnabled())

    def test_saving_an_empty_chain_keeps_failover_usable(self) -> None:
        """후보가 없으면 전환할 곳이 없을 뿐, 설정이 깨지면 안 된다."""
        panel = AiRoutingPanel(self.db)
        panel.persist()
        failover = load_failover_settings(self.db)
        self.assertEqual(failover.chain, [])
        self.assertTrue(failover.enabled)
