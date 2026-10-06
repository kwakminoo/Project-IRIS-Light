"""Launch MainWindow in independent processes against isolated local preferences."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[1])
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready
ensure_qt_webengine_ready()
from PyQt6.QtWidgets import QApplication
from iris.ui.window.main_window import MainWindow
from iris.storage.model_prefs import load_selected_model
app = QApplication([])
win = MainWindow(test_mode=True)
win._settings.hermes_enabled = False
win._verify_api_model_once = lambda model: None
win._sync_iris_wiki = lambda: None
win._handoff_context_to = lambda *args: None
win._schedule_wiki_session_close = lambda *args, **kwargs: None
expected, choose = sys.argv[2:4]
if choose:
    win._chat.set_models(["claude", "gpt"], selected="gpt" if choose == "claude" else "claude")
    win._chat._select_model_runtime(choose)
else:
    assert win._saved_model == expected, (win._saved_model, expected)
win._chat.set_models(["claude", "gpt"], selected=win._saved_model)
assert win._chat.current_model() == expected
old = win._conversation_id
win._chat_session.record("user", "persistence check")
win._on_new_chat_requested()
win._on_conversation_selected(old)
win._apply_iris_ide_unified_layout(True)
assert win._companion_page is not None
assert win._chat.current_model() == expected
win._apply_iris_ide_unified_layout(False)
win._show_assistant_workspace()
win._publish_model_list([], boot=False)
assert win._chat.current_model() == expected
assert load_selected_model(win._db) == expected
print("PROCESS OK", expected, "choice" if choose else "restart", flush=True)
win.close()
app.processEvents()
os._exit(0)
'''
with tempfile.TemporaryDirectory(dir=ROOT / ".iris_light_test_tmp") as tmp:
    for model, choose in [("claude", "claude"), ("claude", ""), ("gpt", "gpt"), ("gpt", "")]:
        result = subprocess.run([sys.executable, "-c", CHILD, str(ROOT), model, choose], cwd=tmp, timeout=60)
        if result.returncode:
            raise SystemExit(result.returncode)
