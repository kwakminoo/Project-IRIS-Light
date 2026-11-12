"""Per-turn tool error limits shared by the Iris sidecar."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field


def _error_text(result: object) -> str:
    raw: object = result
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ""
        try:
            raw = json.loads(text)
        except (TypeError, ValueError):
            return text if text.lower().startswith(("error", "traceback")) else ""
    if not isinstance(raw, dict):
        return ""
    if raw.get("ok") is True and not raw.get("error"):
        return ""
    if raw.get("error"):
        return " ".join(str(raw["error"]).split())
    return "tool returned ok=false" if raw.get("ok") is False else ""


def _target_key(name: str, args: object, error: str) -> str:
    try:
        payload = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        payload = repr(args)
    digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
    return f"{name.strip()}:{digest}:{error}"


@dataclass
class ToolErrorBudget:
    """Stop after one identical target error 3 times or 10 total errors."""

    same_error_limit: int = 3
    total_error_limit: int = 10
    total_errors: int = 0
    repeated: Counter[str] = field(default_factory=Counter)
    reason: str = ""

    def observe(self, name: str, args: object, result: object) -> str:
        if self.reason:
            return self.reason
        error = _error_text(result)
        if not error:
            return ""
        self.total_errors += 1
        key = _target_key(name, args, error)
        self.repeated[key] += 1
        if self.repeated[key] >= self.same_error_limit:
            self.reason = (
                f"Stopped after the same tool target failed {self.same_error_limit} times: "
                f"{name} - {error[:240]}"
            )
        elif self.total_errors >= self.total_error_limit:
            self.reason = (
                f"Stopped after {self.total_error_limit} tool errors in one turn: "
                f"{name} - {error[:240]}"
            )
        return self.reason


def _self_check() -> None:
    failed = '{"ok": false, "error": "missing file"}'
    budget = ToolErrorBudget()
    assert budget.observe("read_file", {"path": "a"}, failed) == ""
    assert budget.observe("read_file", {"path": "a"}, failed) == ""
    assert "3 times" in budget.observe("read_file", {"path": "a"}, failed)

    total = ToolErrorBudget()
    for index in range(9):
        assert total.observe("tool", {"n": index}, failed) == ""
    assert "10 tool errors" in total.observe("tool", {"n": 9}, failed)
    assert ToolErrorBudget().observe("tool", {}, '{"ok": true}') == ""


if __name__ == "__main__":
    _self_check()
    print("tool error budget ok")
