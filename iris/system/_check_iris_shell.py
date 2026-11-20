"""TDD: Iris Shell scoped exec (no console window) + home cwd guard."""

from __future__ import annotations

from pathlib import Path

from iris.system.iris_shell import (
    parse_shell_job,
    resolve_shell_cwd,
    run_shell_job,
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

    print("iris_shell ok")


if __name__ == "__main__":
    main()
