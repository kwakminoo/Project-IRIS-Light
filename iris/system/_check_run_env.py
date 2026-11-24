"""W11-A — scrubbed child env for Execution Runtime / shell hot paths.

Fails when:
- build_child_env leaks *API_KEY* / *SECRET* / *PASSWORD* keys or values
- allowlisted PATH (etc.) dropped from base
- extra IRIS_ENVIRONMENT_ID not preserved
- runtime meta.json / last_run dumps env secrets

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_run_env
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from iris.system.run_env import build_child_env


_SECRET_KEY = "OPENAI_API_KEY"
_SECRET_VAL = "sk-test-w11a-openai-not-real"
_FAKE_SECRET_KEY = "IRIS_FAKE_SECRET"
_FAKE_SECRET_VAL = "w11a-fake-secret-value"
_MAIL_KEY = "MAIL_PASSWORD"
_MAIL_VAL = "w11a-mail-pass-value"


def _check_strips_secrets_keeps_path() -> None:
    base = {
        "PATH": "C:\\Windows\\System32;C:\\fake\\bin",
        "PATHEXT": ".COM;.EXE",
        "SYSTEMROOT": "C:\\Windows",
        _SECRET_KEY: _SECRET_VAL,
        _FAKE_SECRET_KEY: _FAKE_SECRET_VAL,
        _MAIL_KEY: _MAIL_VAL,
        "IRIS_LEAK_TOKEN": "tok-should-go",
        "RANDOM_APP_SETTING": "should-not-pass",
    }
    out = build_child_env(base, None)
    assert "PATH" in out and out["PATH"] == base["PATH"], out
    assert "PATHEXT" in out, out
    assert "SYSTEMROOT" in out, out
    for bad in (_SECRET_KEY, _FAKE_SECRET_KEY, _MAIL_KEY, "IRIS_LEAK_TOKEN", "RANDOM_APP_SETTING"):
        assert bad not in out, f"leaked key {bad}: {out}"
    blob = "\n".join(f"{k}={v}" for k, v in out.items())
    for val in (_SECRET_VAL, _FAKE_SECRET_VAL, _MAIL_VAL, "tok-should-go"):
        assert val not in blob, f"leaked value in env: {val!r}"


def _check_extra_environment_id() -> None:
    base = {"PATH": "C:\\Windows\\System32"}
    out = build_child_env(base, {"IRIS_ENVIRONMENT_ID": "env-w11a-x"})
    assert out.get("IRIS_ENVIRONMENT_ID") == "env-w11a-x", out
    assert "PATH" in out, out


def _check_runtime_meta_no_env_dump() -> None:
    """Runtime must not serialize the scrubbed/full env into meta or last_run."""
    from iris.system.execution_runtime import ExecutionRuntime, ProcessStatus

    rt = ExecutionRuntime(runs_root=Path.home() / ".iris-light" / "runs")
    # Inject synthetic secrets into process env for this spawn path only via
    # the env= kw — build_child_env must strip them; meta must never dump env.
    run_id = rt.start(
        argv=[sys.executable, "-c", "import sys; sys.exit(0)"],
        env={
            _SECRET_KEY: _SECRET_VAL,
            _FAKE_SECRET_KEY: _FAKE_SECRET_VAL,
            _MAIL_KEY: _MAIL_VAL,
            "IRIS_ENVIRONMENT_ID": "meta-check-id",
        },
        env_id="meta-check-id",
    )
    rec = rt.wait(run_id, timeout_s=15.0)
    assert rec.status == ProcessStatus.COMPLETED, rec
    meta_path = Path(rec.stdout_ref).parent / "meta.json"
    assert meta_path.is_file(), meta_path
    meta_text = meta_path.read_text(encoding="utf-8")
    meta = json.loads(meta_text)
    assert "env" not in meta, meta.keys()
    for needle in (_SECRET_VAL, _FAKE_SECRET_VAL, _MAIL_VAL, _SECRET_KEY, _MAIL_KEY):
        assert needle not in meta_text, f"secret in meta.json: {needle!r}"
    # last_run compat is stdout/stderr mirror — secrets must not appear there either
    last = Path.home() / ".iris-light" / "runs" / "last_run.log"
    if last.is_file():
        last_text = last.read_text(encoding="utf-8", errors="replace")
        for needle in (_SECRET_VAL, _FAKE_SECRET_VAL, _MAIL_VAL):
            assert needle not in last_text, f"secret in last_run: {needle!r}"


def main() -> None:
    _check_strips_secrets_keeps_path()
    _check_extra_environment_id()
    _check_runtime_meta_no_env_dump()
    print("run_env ok")


if __name__ == "__main__":
    main()
