"""IDE vibe coding smoke: gugudan / tetris / mini website write+run.

  py -3 -m iris.ui._check_ide_coding_samples
"""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

from iris.system.project_ops import (
    create_scaffold,
    run_project_command,
    summarize_run,
    write_project_file,
    write_project_file_stream,
)


TETRIS = '''\
"""Minimal terminal tetris tick demo (no GUI loop)."""
BOARD_W, BOARD_H = 10, 20
SHAPES = {
    "I": [(0, 1), (1, 1), (2, 1), (3, 1)],
    "O": [(0, 0), (0, 1), (1, 0), (1, 1)],
    "T": [(0, 1), (1, 0), (1, 1), (1, 2)],
}


def empty_board():
    return [["."] * BOARD_W for _ in range(BOARD_H)]


def place(board, shape, x, y, ch="#"):
    for dx, dy in SHAPES[shape]:
        board[y + dy][x + dx] = ch


def render(board):
    return "\\n".join("".join(row) for row in board)


def main():
    board = empty_board()
    place(board, "T", 3, 0)
    place(board, "O", 7, 2)
    place(board, "I", 0, 5)
    print(render(board))
    print("tetris_demo_ok shapes=3")


if __name__ == "__main__":
    main()
'''

WEBSITE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>Iris Sample Site</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <main>
    <h1>Iris Light Sample</h1>
    <p id="msg">hello from iris vibe coding</p>
    <button id="btn" type="button">click</button>
  </main>
  <script src="app.js"></script>
</body>
</html>
"""

WEBSITE_CSS = """
body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
main { max-width: 40rem; margin: 4rem auto; padding: 1.5rem; }
button { padding: 0.5rem 1rem; cursor: pointer; }
"""

WEBSITE_JS = """
document.getElementById('btn').addEventListener('click', () => {
  document.getElementById('msg').textContent = 'clicked';
});
"""


def _run_py(root: Path, rel: str, *, input_text: str | None = None) -> dict:
    return run_project_command(
        root, ["python", rel], timeout_sec=30, input_text=input_text
    )


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="iris-ide-coding-") as td:
        parent = Path(td)

        # 1) gugudan scaffold
        created = create_scaffold(parent, "gugudan-demo", template="gugudan")
        g_root = Path(created["path"])
        g_files = created.get("files") or []
        py = next((f for f in g_files if str(f).endswith(".py")), "gugudan.py")
        ran = _run_py(g_root, str(py), input_text="7\n")
        summary = summarize_run(ran)["summary"]
        out = ran.get("stdout") or ""
        ok = ran.get("exit_code") == 0 and "7 x 9" in out and "63" in out
        results.append(("gugudan scaffold+run", ok, summary))

        # 2) tetris write+stream+run
        t_root = parent / "tetris-demo"
        t_root.mkdir()
        write_project_file(t_root, "README.md", "# tetris demo\n")
        streamed = write_project_file_stream(
            t_root, "tetris.py", TETRIS, chunk_chars=40, chunk_delay_ms=0
        )
        ran = _run_py(t_root, "tetris.py")
        out = ran.get("stdout") or ""
        ok = (
            ran.get("exit_code") == 0
            and "tetris_demo_ok" in out
            and streamed.get("chunks", 0) >= 1
        )
        results.append(("tetris stream+run", ok, summarize_run(ran)["summary"]))

        # 3) mini website files + static check
        w_root = parent / "website-demo"
        w_root.mkdir()
        write_project_file(w_root, "index.html", WEBSITE_HTML)
        write_project_file(w_root, "style.css", WEBSITE_CSS)
        write_project_file(w_root, "app.js", WEBSITE_JS)
        index = w_root / "index.html"
        html = index.read_text(encoding="utf-8")
        ok = (
            index.is_file()
            and (w_root / "style.css").is_file()
            and (w_root / "app.js").is_file()
            and "Iris Light Sample" in html
            and "app.js" in html
        )
        # file:// open is optional (headless CI may skip UI)
        try:
            webbrowser.get()
            # don't actually open browser in automated check
            url_ok = index.as_uri().startswith("file:")
        except Exception:
            url_ok = True
        results.append(("website files", ok and url_ok, f"path={index}"))

        # 4) launcher contract (Windows empty new-window)
        from iris.system import ide_launcher as il

        src = Path(il.__file__).read_text(encoding="utf-8")
        ok = (
            'return _popen_detached([exe, "--new-window"])' in src
            and '["_new-window", root_s]' not in src
            and '[exe, "--new-window", root_s]' not in src
        )
        results.append(("windows empty --new-window contract", ok, "ide_launcher"))

        # 5) bindings default new_window=True
        from iris.ui import control_bindings as cb

        src = Path(cb.__file__).read_text(encoding="utf-8")
        ok = 'args.get("new_window", True)' in src and 'args.get("new_window", False)' not in src
        results.append(("bindings new_window default True", ok, "control_bindings"))

        # 6) exit companion closes Iris-owned Companion only (safe WM_CLOSE)
        from iris.ui.window import main_window as mw

        src = Path(mw.__file__).read_text(encoding="utf-8")
        import re

        m = re.search(
            r"def _exit_ide_companion\(self\).*?(?=\n    def |\Z)", src, re.S
        )
        body = m.group(0) if m else ""
        ok = (
            "_safe_close_companion_ide" in body
            and "_clear_ide_session" in body
            and "_ide_window_owned_by_iris" in src
            and "close_window_by_hwnd" in src
        )
        results.append(("exit companion safe close owned IDE", ok, "main_window"))

        # 7) open_ide_folder waits 14s (Windows)
        m = re.search(r"def _open_ide_folder\(self.*?(?=\n    def |\Z)", src, re.S)
        body = m.group(0) if m else ""
        ok = "14.0" in body or "+ 14" in body
        results.append(("open_ide_folder wait ~14s", ok, "windows timing"))

        # 8) static web preview helpers
        from iris.system import project_ops as po

        src = Path(po.__file__).read_text(encoding="utf-8")
        ok = (
            "def is_static_web_file" in src
            and "def open_preview_in_browser" in src
            and "def infer_dev_server_url" in src
        )
        uri = ""
        try:
            uri = po.static_web_file_uri(w_root, "index.html")
            ok = ok and uri.startswith("file:")
            ok = ok and po.infer_dev_server_url(["python", "-m", "http.server", "8765"]) == (
                "http://127.0.0.1:8765"
            )
        except Exception as exc:
            ok = False
            uri = str(exc)
        results.append(("web browser preview helpers", ok, uri or "project_ops"))

    print("\n=== IDE coding sample report ===")
    failed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {name} - {detail}")
    print(f"total={len(results)} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
