"""Landing contract scrape: Windows done/fail prefers UDP; fail must not pop user.

Hermes Turn ended → sidecar _emit(done/fail) via UDP → host finished_ok → DB.
Stdout-only terminal done wedges the host (tools can finish while UI spins).
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[2]
_SIDECAR = _ROOT / "iris" / "engine" / "_sidecar_main.py"
_RUNTIME = _ROOT / "iris" / "engine" / "runtime.py"
_MAIN_WINDOW = _ROOT / "iris" / "ui" / "window" / "main_window.py"


def _class_method_source(path: Path, class_name: str, method_name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                return ast.get_source_segment(path.read_text(encoding="utf-8"), item) or ""
    raise AssertionError(f"{class_name}.{method_name} missing in {path}")


def _check_sidecar_emit_prefers_udp_scrape() -> None:
    src = _SIDECAR.read_text(encoding="utf-8")
    assert "def _emit_terminal_via_udp" in src, "UDP terminal emit helper missing"
    assert "IRIS_TERMINAL_UDP_PORT" in src, "sidecar must read IRIS_TERMINAL_UDP_PORT"
    # done/fail branch must call UDP before return (not host stdout write).
    import iris.engine._sidecar_main as sidecar

    emit_src = inspect.getsource(sidecar._emit)
    assert 'kind in ("done", "fail")' in emit_src or "kind in ('done', 'fail')" in emit_src, (
        emit_src
    )
    done_idx = emit_src.find('("done", "fail")')
    if done_idx < 0:
        done_idx = emit_src.find("('done', 'fail')")
    assert done_idx >= 0, emit_src
    ret_idx = emit_src.find("\n        return", done_idx)
    assert ret_idx > done_idx, emit_src
    branch = emit_src[done_idx:ret_idx]
    assert "_emit_terminal_via_udp(payload)" in branch, branch
    assert "_write_host_bytes" not in branch, (
        "done/fail branch must not write host stdout"
    )


def _check_host_product_binds_udp_scrape() -> None:
    src = _RUNTIME.read_text(encoding="utf-8")
    assert "def _bind_terminal_udp" in src
    assert "terminal_udp_port" in src
    # Product run_turn must bind UDP and pass the port into the turn command.
    assert "_bind_terminal_udp()" in src, "host must bind UDP for each turn"
    assert "terminal_udp_port=udp_port" in src or "terminal_udp_port=udp_port," in src, src
    assert "udp_sock.recvfrom" in src, "host must read terminal done/fail from UDP"


def _check_fail_does_not_pop_user_scrape() -> None:
    fail_src = _class_method_source(_MAIN_WINDOW, "MainWindow", "_on_chat_failed")
    away_src = _class_method_source(_MAIN_WINDOW, "MainWindow", "_fail_slot_away")
    for name, body in (("_on_chat_failed", fail_src), ("_fail_slot_away", away_src)):
        assert "pop_last_user_message" not in body, f"{name} must not pop user"
        assert "_drop_last_user_history" not in body, f"{name} must not drop user"
        assert "drop_last_user" not in body, f"{name} must not drop user"


def _check_emit_done_uses_udp_not_stdout() -> None:
    """Behavioral: done hits localhost UDP; host stdout write is not used."""
    import iris.engine._sidecar_main as sidecar

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(1.0)
    port = int(sock.getsockname()[1])
    host_writes: list[bytes] = []
    previous = os.environ.get("IRIS_TERMINAL_UDP_PORT")
    os.environ["IRIS_TERMINAL_UDP_PORT"] = str(port)
    try:
        with (
            patch.object(
                sidecar,
                "_write_host_bytes",
                side_effect=lambda _fd, data: host_writes.append(bytes(data)),
            ),
            patch.object(sidecar, "_write_terminal_file", side_effect=AssertionError("file")),
        ):
            sidecar._emit({"t": "done", "text": "udp-prefer-land"})
            sidecar._emit({"t": "fail", "code": "x", "detail": "udp-prefer-fail"})
        got_done = sock.recvfrom(65535)[0].decode("utf-8")
        got_fail = sock.recvfrom(65535)[0].decode("utf-8")
    finally:
        sock.close()
        if previous is None:
            os.environ.pop("IRIS_TERMINAL_UDP_PORT", None)
        else:
            os.environ["IRIS_TERMINAL_UDP_PORT"] = previous

    assert host_writes == [], host_writes
    done_obj = json.loads(got_done.strip().splitlines()[0])
    fail_obj = json.loads(got_fail.strip().splitlines()[0])
    assert done_obj.get("t") == "done" and done_obj.get("text") == "udp-prefer-land", done_obj
    assert fail_obj.get("t") == "fail" and fail_obj.get("detail") == "udp-prefer-fail", fail_obj


def _check_emit_fail_udp_missing_falls_to_file_not_stdout() -> None:
    """UDP miss may use terminal file backup; still must not use stdout for done/fail."""
    import iris.engine._sidecar_main as sidecar

    host_writes: list[bytes] = []
    previous = os.environ.pop("IRIS_TERMINAL_UDP_PORT", None)
    with tempfile.TemporaryDirectory(prefix="iris-term-") as tmp:
        os.environ["IRIS_TERMINAL_DIR"] = tmp
        try:
            with patch.object(
                sidecar,
                "_write_host_bytes",
                side_effect=lambda _fd, data: host_writes.append(bytes(data)),
            ):
                sidecar._emit({"t": "done", "text": "file-backup-ok"})
            blobs = [
                p.read_text(encoding="utf-8")
                for p in Path(tmp).iterdir()
                if p.is_file()
            ]
        finally:
            os.environ.pop("IRIS_TERMINAL_DIR", None)
            if previous is not None:
                os.environ["IRIS_TERMINAL_UDP_PORT"] = previous

    assert host_writes == [], host_writes
    assert any("file-backup-ok" in b for b in blobs), blobs


def main() -> None:
    _check_sidecar_emit_prefers_udp_scrape()
    _check_host_product_binds_udp_scrape()
    _check_fail_does_not_pop_user_scrape()
    _check_emit_done_uses_udp_not_stdout()
    _check_emit_fail_udp_missing_falls_to_file_not_stdout()
    print("landing udp contract ok")


if __name__ == "__main__":
    main()
