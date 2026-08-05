"""Vibe reveal/run 자가점검 (디스크·헬퍼; IDE GUI 타이핑/터미널은 수동).

  py -3 -m iris.ui._check_vibe_reveal
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.system.ide_launcher import open_file_in_ide, resolve_ide_cli
from iris.system.project_ops import (
    build_iris_terminal_command,
    build_run_command,
    run_project_command,
    summarize_run,
    upsert_iris_run_task,
    write_project_file,
    write_project_file_stream,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="iris-vibe-", ignore_cleanup_errors=True) as td:
        root = Path(td)

        w = write_project_file(root, "hello.py", "print('hi')\n")
        assert Path(w["path"]).is_file(), "write_file"
        print("ok write_file", w["rel_path"])

        text = "alpha\nbeta\ngamma\n" * 5
        s = write_project_file_stream(
            root, "stream.py", text, chunk_chars=10, chunk_delay_ms=0
        )
        assert Path(s["path"]).read_text(encoding="utf-8") == text
        print("ok stream", s["chunks"], "chunks")

        write_project_file(root, "add.py", "print(1+2)\n")
        argv = build_run_command(file="add.py")
        result = run_project_command(root, argv, timeout_sec=20)
        assert result["exit_code"] == 0 and "3" in (result.get("stdout") or "")
        shell = build_iris_terminal_command(argv)
        assert ("Tee-Object" in shell or " tee " in shell) and "last_run.log" in shell
        tasks = upsert_iris_run_task(root, shell)
        body = Path(tasks).read_text(encoding="utf-8")
        assert "Iris: Run" in body and ("powershell" in body.lower() or "/bin/bash" in body)
        print("ok terminal task", summarize_run(result)["summary"][:60])

        from iris.automation import ide_input

        assert ide_input.get_window_title(0) == ""
        print("ok ide_input import")

        cli = resolve_ide_cli("cursor")
        if cli:
            ok, err = open_file_in_ide("cursor", str(root / "hello.py"), reuse_window=True)
            print("ok open_file_in_ide", ok, err or "")
        else:
            print("skip open_file (no cursor cli)")

    print("vibe_reveal check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
