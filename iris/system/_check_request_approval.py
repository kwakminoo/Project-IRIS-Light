"""U03 — request-scoped approval ledger contracts."""

from __future__ import annotations

import time

from iris.system.request_approval import (
    RequestApprovalLedger,
    fingerprint_from_manage_args,
    normalize_execution_fingerprint,
)


def main() -> None:
    led = RequestApprovalLedger()
    fp = normalize_execution_fingerprint(shell="echo hi", cwd="/tmp")
    rec = led.grant(fingerprint=fp, session_id="s1", workspace_id="ws")
    ok, reason = led.consume(
        request_id=rec.request_id, fingerprint=fp, session_id="s1", workspace_id="ws"
    )
    assert ok, reason
    ok2, reason2 = led.consume(
        request_id=rec.request_id, fingerprint=fp, session_id="s1", workspace_id="ws"
    )
    assert not ok2 and "used" in reason2

    # Fingerprint change after approve → deny
    rec2 = led.grant(fingerprint=fp, session_id="s1")
    other = normalize_execution_fingerprint(shell="echo bye", cwd="/tmp")
    ok3, reason3 = led.consume(
        request_id=rec2.request_id, fingerprint=other, session_id="s1"
    )
    assert not ok3 and "fingerprint" in reason3

    # cwd change
    fp_a = fingerprint_from_manage_args({"command": "echo x", "cwd": "/a"})
    fp_b = fingerprint_from_manage_args({"command": "echo x", "cwd": "/b"})
    assert fp_a != fp_b

    # Concurrent isolations
    r1 = led.grant(fingerprint=fp, session_id="sA")
    r2 = led.grant(fingerprint=fp, session_id="sB")
    assert r1.request_id != r2.request_id
    ok_a, _ = led.consume(request_id=r1.request_id, fingerprint=fp, session_id="sA")
    ok_b, reason_b = led.consume(
        request_id=r1.request_id, fingerprint=fp, session_id="sB"
    )
    assert ok_a and not ok_b

    # Expire
    short = led.grant(fingerprint=fp, session_id="s1", ttl_s=0.05)
    time.sleep(0.08)
    ok_e, reason_e = led.consume(
        request_id=short.request_id, fingerprint=fp, session_id="s1"
    )
    assert not ok_e
    assert ("expir" in reason_e) or ("unknown" in reason_e), reason_e

    # Reject
    rej = led.reject(fingerprint=fp, session_id="s1")
    ok_r, reason_r = led.consume(
        request_id=rej.request_id, fingerprint=fp, session_id="s1"
    )
    assert not ok_r and "not granted" in reason_r

    # Session cleanup
    kept = led.grant(fingerprint=fp, session_id="kill-me")
    assert led.cleanup_session("kill-me") >= 1
    assert led.get(kept.request_id) is None

    # process.py must not use global True bypass
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "ui" / "control_actions" / "process.py"
    body = src.read_text(encoding="utf-8")
    assert "default_approval_ledger" in body
    assert "lambda _spec, _a: True" not in body
    assert "lambda _s, _a: True" not in body

    print("request_approval ok")


if __name__ == "__main__":
    main()
