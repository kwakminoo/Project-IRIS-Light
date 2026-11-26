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

    # Grant with workspace → empty caller workspace must not skip match
    rec_ws = led.grant(fingerprint=fp, session_id="s1", workspace_id="ws-strict")
    ok_empty, reason_empty = led.consume(
        request_id=rec_ws.request_id, fingerprint=fp, session_id="s1", workspace_id=""
    )
    assert not ok_empty and "workspace" in reason_empty, reason_empty

    # FPR-03: tool_call_id on grant → consume must match (empty ≠ skip)
    rec_tc = led.grant(
        fingerprint=fp, session_id="s1", tool_call_id="call-abc"
    )
    ok_tc_miss, reason_tc = led.consume(
        request_id=rec_tc.request_id, fingerprint=fp, session_id="s1"
    )
    assert not ok_tc_miss and "tool_call" in reason_tc, reason_tc
    ok_tc_ok, _ = led.consume(
        request_id=rec_tc.request_id,
        fingerprint=fp,
        session_id="s1",
        tool_call_id="call-abc",
    )
    assert ok_tc_ok

    # Grant without tool_call_id → omit kwarg still consumes (compat)
    rec_plain = led.grant(fingerprint=fp, session_id="s1")
    ok_plain, reason_plain = led.consume(
        request_id=rec_plain.request_id, fingerprint=fp, session_id="s1"
    )
    assert ok_plain, reason_plain

    # Concurrent same fingerprint / different sessions never share (already above);
    # same command string ≠ shared request_id.
    same_cmd = fingerprint_from_manage_args({"command": "echo same", "cwd": "/x"})
    g_a = led.grant(fingerprint=same_cmd, session_id="sess-1")
    g_b = led.grant(fingerprint=same_cmd, session_id="sess-2")
    assert g_a.request_id != g_b.request_id
    ok_cross, reason_cross = led.consume(
        request_id=g_a.request_id, fingerprint=same_cmd, session_id="sess-2"
    )
    assert not ok_cross and "session" in reason_cross, reason_cross
    ok_own, _ = led.consume(
        request_id=g_a.request_id, fingerprint=same_cmd, session_id="sess-1"
    )
    assert ok_own

    # Fingerprint covers exe (argv[0]) — mutation after grant fails consume
    fp_exe_a = fingerprint_from_manage_args(
        {"argv": ["python", "-c", "pass"], "cwd": "/t"}
    )
    fp_exe_b = fingerprint_from_manage_args(
        {"argv": ["pythonw", "-c", "pass"], "cwd": "/t"}
    )
    assert fp_exe_a != fp_exe_b
    g_exe = led.grant(fingerprint=fp_exe_a, session_id="s1")
    ok_mut, reason_mut = led.consume(
        request_id=g_exe.request_id, fingerprint=fp_exe_b, session_id="s1"
    )
    assert not ok_mut and "fingerprint" in reason_mut, reason_mut

    # process.py must not use global True bypass / set_human_confirm (HF-04)
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "ui" / "control_actions" / "process.py"
    body = src.read_text(encoding="utf-8")
    assert "default_approval_ledger" in body
    assert "lambda _spec, _a: True" not in body
    assert "lambda _s, _a: True" not in body
    assert "rt.set_human_confirm(" not in body, "HF-04: process.manage must not mutate Runtime confirm"
    assert "tool_call_id=" in body, "FPR-03: grant must bind tool_call_id from ctx"
    assert "finalize_process_start_plan" in body, "card grant must use finalized plan"
    assert "plan.fingerprint()" in body, "grant fingerprint must come from finalized plan"
    assert "fingerprint_from_manage_args" not in body, "raw manage fingerprint must not grant"

    # Runtime consume order: finalize before ledger.consume
    rt_src = Path(__file__).resolve().parent / "execution_runtime.py"
    rt_body = rt_src.read_text(encoding="utf-8")
    fin_at = rt_body.find("finalize_process_start_plan(")
    consume_at = rt_body.find("default_approval_ledger().consume(")
    assert fin_at >= 0 and consume_at >= 0, "finalize + consume must both exist"
    assert fin_at < consume_at, "finalize must run before ledger consume"

    print("request_approval ok")


if __name__ == "__main__":
    main()
