"""채팅용 제한 Python 실행 → matplotlib PNG (Code Interpreter 축소판)."""

from __future__ import annotations

import ast
import concurrent.futures
import contextlib
import io
import uuid
from pathlib import Path
from typing import Any

_ALLOWED_ROOTS = frozenset(
    {
        "numpy",
        "matplotlib",
        "PIL",
        "math",
        "json",
        "collections",
        "itertools",
        "functools",
        "re",
        "typing",
    }
)


def plots_dir() -> Path:
    root = Path.home() / ".iris-light" / "runtime" / "plots"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_chat_python(code: str, *, timeout_s: float = 20) -> dict[str, Any]:
    """화이트리스트 import + Agg 백엔드. 열린 figure 를 plots/ 에 저장."""
    source = (code or "").strip()
    if not source:
        return {"ok": False, "stdout": "", "stderr": "", "png_paths": [], "error": "code required", "chat_markdown": ""}
    try:
        timeout = float(timeout_s)
    except (TypeError, ValueError):
        timeout = 20.0
    timeout = max(1.0, min(timeout, 60.0))

    err = _forbidden_imports(source)
    if err:
        return {"ok": False, "stdout": "", "stderr": "", "png_paths": [], "error": err, "chat_markdown": ""}

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_run_body, source)
        try:
            result = fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "png_paths": [],
                "error": f"timeout after {timeout:.0f}s",
                "chat_markdown": "",
            }
    return result


def _forbidden_imports(source: str) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"syntax error: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = (alias.name or "").split(".", 1)[0]
                if root not in _ALLOWED_ROOTS:
                    return f"import not allowed: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                return "relative import not allowed"
            mod = node.module or ""
            root = mod.split(".", 1)[0]
            if root not in _ALLOWED_ROOTS:
                return f"import not allowed: {mod or '*'}"
    return None


def _run_body(source: str) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np

    stdout = io.StringIO()
    stderr = io.StringIO()
    ns: dict[str, Any] = {
        "__name__": "__chat_exec__",
        "np": np,
        "numpy": np,
        "plt": plt,
        "matplotlib": matplotlib,
    }
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            compiled = compile(source, "<chat.exec_python>", "exec")
            exec(compiled, ns, ns)  # noqa: S102 — AST-gated whitelist only
            if "plt" in ns:
                plt = ns["plt"]
            paths = _save_figures(plt)
    except Exception as exc:
        return {
            "ok": False,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "png_paths": [],
            "error": f"{type(exc).__name__}: {exc}",
            "chat_markdown": "",
        }

    md_parts = []
    for p in paths:
        posix = Path(p).resolve().as_posix()
        md_parts.append(f"![plot]({posix})")
    return {
        "ok": True,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "png_paths": paths,
        "error": "",
        "chat_markdown": "\n\n".join(md_parts),
    }


def _save_figures(plt: Any) -> list[str]:
    out: list[str] = []
    root = plots_dir()
    for num in list(plt.get_fignums()):
        fig = plt.figure(num)
        name = f"plot-{uuid.uuid4().hex[:12]}.png"
        path = root / name
        fig.savefig(path, dpi=120, bbox_inches="tight")
        out.append(str(path.resolve()))
    plt.close("all")
    return out
