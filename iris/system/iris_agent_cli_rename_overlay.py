"""F3 — materialize real iris_agent_cli; hermes_cli becomes reverse shim.

Install-time overlay on agent checkout root. Soft-fail on Windows locks;
never raise. When rename of physical hermes_cli fails after copy, leave
upstream tree and document partial success so F2 can still plant forward
shims only if iris_agent_cli was not materialized.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_RENAME_STAMP = ".iris-agent-cli-renamed"
_REVERSE_MARKER = "Iris CLI reverse shim — re-exports iris_agent_cli"
_FORWARD_MARKER = "Iris CLI shim — re-exports hermes_cli"
_IRIS_CLI_MARKER = "Iris CLI shim — re-exports iris_agent_cli"

_TEXT_SUFFIXES = {".py", ".pyi", ".toml", ".md", ".txt", ".cfg", ".ini", ".json", ".yml", ".yaml"}

_REVERSE_INIT = f'''\
"""{_REVERSE_MARKER} (F3 install overlay)."""
from iris_agent_cli import *  # noqa: F401, F403
'''

_REVERSE_MAIN = '''\
"""Forward ``-m hermes_cli.main`` to iris_agent_cli.main."""
from iris_agent_cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
'''

_IRIS_CLI_INIT = f'''\
"""{_IRIS_CLI_MARKER} (F3 install overlay)."""
from iris_agent_cli import *  # noqa: F401, F403
'''

_IRIS_CLI_MAIN = '''\
"""Forward ``-m iris_cli.main`` to iris_agent_cli.main."""
from iris_agent_cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
'''


def iris_agent_cli_is_forward_shim(agent_root: Path) -> bool:
    """True when iris_agent_cli is the thin F2 re-export of hermes_cli."""
    init = Path(agent_root) / "iris_agent_cli" / "__init__.py"
    if not init.is_file():
        return False
    try:
        text = init.read_text(encoding="utf-8")
    except OSError:
        return False
    return _FORWARD_MARKER in text or "from hermes_cli import" in text


def iris_agent_cli_is_real_package(agent_root: Path) -> bool:
    """True when iris_agent_cli exists and is not an F2 forward shim."""
    root = Path(agent_root)
    pkg = root / "iris_agent_cli"
    if not pkg.is_dir():
        return False
    init = pkg / "__init__.py"
    if not init.is_file():
        return False
    if iris_agent_cli_is_forward_shim(root):
        return False
    return True


def hermes_cli_is_reverse_shim(agent_root: Path) -> bool:
    init = Path(agent_root) / "hermes_cli" / "__init__.py"
    if not init.is_file():
        return False
    try:
        text = init.read_text(encoding="utf-8")
    except OSError:
        return False
    return _REVERSE_MARKER in text or "from iris_agent_cli import" in text


def iris_agent_cli_rename_applied(agent_root: Path) -> bool:
    """True when F3 end-state holds: real iris_agent_cli + reverse hermes_cli."""
    root = Path(agent_root)
    if not iris_agent_cli_is_real_package(root):
        return False
    hermes = root / "hermes_cli"
    if not hermes.exists():
        return True
    return hermes_cli_is_reverse_shim(root)


def apply_iris_agent_cli_rename_overlay(agent_root: Path) -> list[str]:
    """Copy+rewrite hermes_cli → iris_agent_cli; reverse-shim hermes_cli. Soft-fail."""
    root = Path(agent_root)
    hermes = root / "hermes_cli"
    if not hermes.is_dir():
        return ["cli rename: hermes_cli missing — skipped"]

    if iris_agent_cli_rename_applied(root):
        msgs = _ensure_iris_cli_shim(root)
        if msgs:
            return [f"cli rename: already applied; {msgs[0]}"]
        return ["cli rename: already applied"]

    messages: list[str] = []
    iris = root / "iris_agent_cli"

    # Drop F2 forward shim so copy can land a real tree.
    if iris_agent_cli_is_forward_shim(root):
        try:
            shutil.rmtree(iris)
            messages.append("cli rename: removed F2 forward shim")
        except OSError as exc:
            return [
                f"cli rename: cannot clear F2 shim ({exc}) — fall back to F2 dual-accept path"
            ]

    if not iris_agent_cli_is_real_package(root):
        try:
            if iris.exists():
                shutil.rmtree(iris)
            shutil.copytree(hermes, iris)
        except OSError as exc:
            return [
                f"cli rename: copy fail ({exc}) — fall back to F2 dual-accept path"
            ]
        try:
            n = _rewrite_tree_agent_to_iris(iris)
            messages.append(f"cli rename: materialized iris_agent_cli ({n} files rewritten)")
        except OSError as exc:
            return [
                f"cli rename: rewrite fail ({exc}) — fall back to F2 dual-accept path"
            ]
    else:
        messages.append("cli rename: iris_agent_cli already real")

    # Replace physical hermes_cli with reverse shim.
    replace_ok, replace_msg = _replace_agent_with_reverse_shim(root)
    messages.append(replace_msg)
    if not replace_ok:
        messages.append(
            "cli rename: soft-fail — hermes_cli left as upstream; "
            "iris_agent_cli real; probe uses iris_* only"
        )
        messages.extend(_ensure_iris_cli_shim(root))
        _try_stamp(root)
        return messages

    messages.extend(_ensure_iris_cli_shim(root))
    _try_stamp(root)
    return messages


def _rewrite_tree_agent_to_iris(pkg_dir: Path) -> int:
    count = 0
    for path in pkg_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.suffix:
            continue
        if path.suffix == "" and path.name not in ("Makefile", "Dockerfile"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "hermes_cli" not in text:
            continue
        path.write_text(
            text.replace("hermes_cli", "iris_agent_cli"),
            encoding="utf-8",
            newline="\n" if path.suffix == ".py" else None,
        )
        count += 1
    return count


def _replace_agent_with_reverse_shim(root: Path) -> tuple[bool, str]:
    hermes = root / "hermes_cli"
    if hermes_cli_is_reverse_shim(root):
        return True, "cli rename: hermes_cli already reverse shim"

    bak = root / "hermes_cli._f3_upstream"
    try:
        if bak.exists():
            shutil.rmtree(bak)
        hermes.rename(bak)
    except OSError as exc:
        # Locked on Windows: leave upstream tree intact.
        return False, f"cli rename: hermes_cli rename locked ({exc})"

    try:
        hermes.mkdir(parents=True, exist_ok=True)
        (hermes / "__init__.py").write_text(_REVERSE_INIT, encoding="utf-8", newline="\n")
        (hermes / "main.py").write_text(_REVERSE_MAIN, encoding="utf-8", newline="\n")
    except OSError as exc:
        # Try to put upstream back.
        try:
            if hermes.exists():
                shutil.rmtree(hermes)
            bak.rename(hermes)
        except OSError:
            pass
        return False, f"cli rename: reverse shim write fail ({exc})"

    # Best-effort cleanup of backup; keep if locked.
    try:
        shutil.rmtree(bak)
    except OSError:
        return True, "cli rename: reverse shim ok (upstream bak kept)"
    return True, "cli rename: hermes_cli → reverse shim"


def _ensure_iris_cli_shim(root: Path) -> list[str]:
    pkg = root / "iris_cli"
    written: list[str] = []
    try:
        pkg.mkdir(parents=True, exist_ok=True)
        init = pkg / "__init__.py"
        if not _file_contains(init, "from iris_agent_cli import"):
            init.write_text(_IRIS_CLI_INIT, encoding="utf-8", newline="\n")
            written.append("iris_cli/__init__.py")
        main = pkg / "main.py"
        if not _file_contains(main, "iris_agent_cli.main"):
            main.write_text(_IRIS_CLI_MAIN, encoding="utf-8", newline="\n")
            written.append("iris_cli/main.py")
    except OSError as exc:
        return [f"cli rename: iris_cli shim fail ({exc})"]
    if written:
        return [f"cli rename: wrote {', '.join(written)}"]
    return []


def _file_contains(path: Path, needle: str) -> bool:
    if not path.is_file():
        return False
    try:
        return needle in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _try_stamp(root: Path) -> None:
    try:
        (root / _RENAME_STAMP).write_text("f3\n", encoding="utf-8")
    except OSError:
        pass
