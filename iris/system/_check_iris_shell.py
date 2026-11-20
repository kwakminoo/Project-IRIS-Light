"""TDD: Iris Shell scoped exec (no console window) + home cwd guard."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from iris.system.iris_shell import (
    ShellJob,
    parse_shell_job,
    resolve_shell_cwd,
    run_shell_job,
    stream_shell_job,
    outcome_as_result,
)


def main() -> None:
    home = Path.home().resolve()
    assert resolve_shell_cwd(None) == home
    assert resolve_shell_cwd("") == home
    assert resolve_shell_cwd(str(home)) == home

    try:
        resolve_shell_cwd("relative/path")
        raise AssertionError("relative cwd must fail")
    except ValueError:
        pass

    outside = Path(home.anchor) / "Windows" if home.anchor else Path("/")
    if outside.exists():
        try:
            resolve_shell_cwd(str(outside))
            raise AssertionError("cwd outside home must fail")
        except ValueError:
            pass

    try:
        parse_shell_job({})
        raise AssertionError("empty command must fail")
    except ValueError:
        pass

    job = parse_shell_job({"command": "echo iris-shell-ok", "cwd": str(home)})
    assert job.cwd == home
    out = run_shell_job(job)
    assert out.via == "iris_shell"
    assert out.ok, (out.stderr, out.stdout, out.summary)
    assert "iris-shell-ok" in (out.stdout + out.stderr)
    assert out.exit_code == 0

    payload = outcome_as_result(out)
    assert payload["via"] == "iris_shell"
    assert payload["exit_code"] == 0
    assert "command" in payload and "stdout" in payload

    # stream_shell_job: chunks must arrive before the call returns
    returned = threading.Event()
    chunks: list[str] = []

    def on_chunk(text: str) -> None:
        assert not returned.is_set(), "on_chunk after stream_shell_job returned"
        chunks.append(text)

    # Sleep between two prints so on_chunk can fire before return.
    if os.name == "nt":
        stream_cmd = "echo hello-stream& ping -n 2 127.0.0.1 >nul& echo bye-stream"
    else:
        stream_cmd = "echo hello-stream; sleep 0.6; echo bye-stream"
    stream_job = ShellJob(command=stream_cmd, cwd=home, timeout_s=15.0)
    stream_out = stream_shell_job(stream_job, on_chunk)
    returned.set()
    assert chunks, "on_chunk never called"
    joined = "".join(chunks)
    assert "hello-stream" in joined, joined
    assert stream_out.ok, (stream_out.stderr, stream_out.stdout, stream_out.summary)
    assert "hello-stream" in (stream_out.stdout + stream_out.stderr)
    stream_payload = outcome_as_result(stream_out)
    assert stream_payload["exit_code"] == 0

    print("iris_shell ok")


if __name__ == "__main__":
    main()
