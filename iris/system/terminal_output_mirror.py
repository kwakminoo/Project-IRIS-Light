"""Pure helpers — Execution Runtime stdout/stderr → IDE terminal mirror cursors.

Runtime owns the process. Theia only displays. Bridge failure must not mark the run failed.
"""

from __future__ import annotations

from typing import Any


def format_run_banner(run_id: str) -> str:
    rid = str(run_id or "").strip() or "?"
    return f"\r\n── IRIS run {rid} ──\r\n"


def advance_output_cursor(chunk: dict[str, Any] | None, *, offset: int) -> tuple[str, int]:
    """Return (text, next_offset) from ExecutionRuntime.read_output payload."""
    data = chunk if isinstance(chunk, dict) else {}
    text = str(data.get("text") or "")
    start = int(data.get("offset") if data.get("offset") is not None else offset)
    if start < 0:
        start = 0
    return text, start + len(text)


def merge_stderr_into_mirror(stdout_text: str, stderr_text: str) -> str:
    """Optional combined dump for a final flush (stderr after stdout)."""
    out = str(stdout_text or "")
    err = str(stderr_text or "")
    if not err:
        return out
    if not out:
        return err
    if out.endswith("\n") or out.endswith("\r"):
        return out + err
    return out + "\n" + err


def _self_check() -> None:
    assert "abc" in format_run_banner("abc")
    text, nxt = advance_output_cursor({"text": "hi", "offset": 0}, offset=0)
    assert text == "hi" and nxt == 2
    text2, nxt2 = advance_output_cursor({"text": "yo", "offset": 2}, offset=2)
    assert text2 == "yo" and nxt2 == 4
    assert merge_stderr_into_mirror("a\n", "e") == "a\ne"
    assert merge_stderr_into_mirror("", "e") == "e"
    print("terminal_output_mirror ok")


if __name__ == "__main__":
    _self_check()
