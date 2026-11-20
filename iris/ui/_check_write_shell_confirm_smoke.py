"""Write+shell confirm smoke: ActionRegistry.invoke via card confirm (no HUD hang)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from iris.system.control_surface import ActionRegistry
from iris.ui.chat.shell_approval import ApprovalState
from iris.ui.control_bindings import _register_actions, human_confirm_decision


class _FakeChat:
    def __init__(self) -> None:
        self.inserts: list[dict] = []
        self._n = 0

    def insert_tool_block(self, **kwargs) -> str:
        self._n += 1
        self.inserts.append(kwargs)
        return f"card-{self._n}"


class _SystemScopeDb:
    def get_preference(self, _key: str, default: object = None) -> object:
        return "system"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _evidence_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = (
        _project_root()
        / ".iris_light_test_tmp"
        / "verify-iris"
        / f"residual-write-shell-{stamp}"
    )
    out.mkdir(parents=True, exist_ok=True)
    return out


def _surface(chat: _FakeChat) -> tuple[MagicMock, ActionRegistry, list[str]]:
    window = MagicMock()
    window._control_qt_invoker = None
    window._ui_mode = "chat"
    window._db = _SystemScopeDb()
    window._chat = chat
    window._get_bound_ide_session.return_value = None
    window._companion_page = None
    window._chat_session = None
    window._note_tool_file_write = MagicMock()

    surface = MagicMock()
    surface.registry = ActionRegistry()
    surface.booting = False
    _register_actions(window, surface)

    hud_calls: list[str] = []

    def _ask_hud() -> bool:
        hud_calls.append("hud")
        return False

    # Card path: pending insert + wait("run"). HUD must not run (15s hang risk).
    surface.registry.set_human_confirm(
        lambda spec, args: human_confirm_decision(
            spec,
            args if isinstance(args, dict) else {},
            chat=chat,
            ask_hud=_ask_hud,
            on_ui=lambda fn: fn(),
            wait=lambda _bid: "run",
            load_approval=lambda: ApprovalState(),
        )
    )
    return window, surface.registry, hud_calls


def _write_summary(
    out_dir: Path,
    *,
    write_ok: bool,
    shell_ok: bool,
    errors: list[str],
    mode: str,
) -> Path:
    payload = {
        "write_ok": write_ok,
        "shell_ok": shell_ok,
        "errors": errors,
        "mode": mode,
        "evidence_dir": str(out_dir),
    }
    path = out_dir / "summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    out_dir = _evidence_dir()
    errors: list[str] = []
    write_ok = False
    shell_ok = False
    mode = "headless"

    chat = _FakeChat()
    _window, reg, hud_calls = _surface(chat)

    assert reg.spec("local.write_file") is not None
    assert reg.spec("local.write_file").confirm_required is True
    assert reg.spec("shell.run") is not None
    assert reg.spec("shell.run").confirm_required is True

    probe = out_dir / "probe_write.txt"
    content = "write-shell-confirm-smoke\n"
    write_out = reg.invoke(
        "local.write_file",
        {"path": str(probe), "content": content},
    )
    if write_out.get("ok") and probe.is_file() and probe.read_text(encoding="utf-8") == content:
        write_ok = True
    else:
        errors.append(f"write: {write_out}")

    marker = out_dir / "shell_marker.txt"
    # cwd under user home (shell contract). No nested quotes — cmd /c echo redirect.
    shell_out = reg.invoke(
        "shell.run",
        {
            "command": f"echo shell-ok>{marker.name}",
            "cwd": str(out_dir),
            "timeout_s": 15,
        },
    )
    if shell_out.get("ok") and marker.is_file() and "shell-ok" in marker.read_text(encoding="utf-8"):
        shell_ok = True
    else:
        errors.append(f"shell: {shell_out}")

    if hud_calls:
        errors.append(f"hud_called: {hud_calls}")
        write_ok = False
        shell_ok = False

    pending = [row for row in chat.inserts if row.get("phase") == "pending"]
    if len(pending) < 2:
        errors.append(f"card_pending_count={len(pending)} inserts={chat.inserts}")

    summary_path = _write_summary(
        out_dir,
        write_ok=write_ok,
        shell_ok=shell_ok,
        errors=errors,
        mode=mode,
    )
    print(f"summary={summary_path}")
    print(f"write_ok={write_ok} shell_ok={shell_ok} mode={mode}")
    if errors:
        for err in errors:
            print(f"error: {err}")
    if not (write_ok and shell_ok and not errors):
        return 1
    print("write shell confirm smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
