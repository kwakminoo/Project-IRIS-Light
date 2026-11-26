"""Workspace Environment Manager — common interpreter picker for all execution paths.

Priority (resolve) — first match wins:
  1. user-selected interpreter path
  2. active shell markers: VIRTUAL_ENV, then CONDA_PREFIX (runnable prefix only)
  3. project .venv at root, then walk-up from file (IDE parity)
  4. uv / poetry / conda discovery only when binary+env are actually runnable
     (lockfile presence alone ≠ supported — see locks)
  5. system python on PATH (never Iris product sys.executable)
  6. create project .venv only if allow_create=True (hot paths default False)

allow_create defaults False on all hot paths — never create venv or install
packages without approval.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from iris.system.win_subprocess import no_window_kwargs

_SOURCE_USER = "user"
_SOURCE_VIRTUAL_ENV = "virtual_env"
_SOURCE_CONDA = "conda"
_SOURCE_VENV = "venv"
_SOURCE_UV = "uv"
_SOURCE_POETRY = "poetry"
_SOURCE_SYSTEM = "system"
_SOURCE_CREATED = "created"
_SOURCE_NONE = "none"

_PYTHON_LAUNCHER_NAMES = frozenset({"python", "python.exe", "python3", "python3.exe", "py", "py.exe"})


def venv_python_at(root: Path) -> Path:
    root = Path(root)
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def python_in_prefix(prefix: str | Path) -> Path | None:
    """Interpreter under a venv/conda prefix, if the file exists."""
    base = Path(prefix).expanduser()
    try:
        base = base.resolve()
    except OSError:
        return None
    if sys.platform == "win32":
        cands = (
            base / "python.exe",
            base / "Scripts" / "python.exe",
        )
    else:
        cands = (
            base / "bin" / "python",
            base / "bin" / "python3",
        )
    for cand in cands:
        if cand.is_file():
            return cand
    return None


def find_venv_python(root: str | Path) -> Path | None:
    cand = venv_python_at(Path(root).expanduser().resolve())
    return cand if cand.is_file() else None


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def walk_up_venv_python(
    start: str | Path,
    *,
    max_levels: int = 64,
) -> tuple[Path, Path] | None:
    """Return (python, venv_root) walking from start upward. Find-only."""
    dir_p = Path(start).expanduser().resolve()
    if dir_p.is_file():
        dir_p = dir_p.parent
    for _ in range(max_levels):
        py = find_venv_python(dir_p)
        if py is not None:
            return py, dir_p
        parent = dir_p.parent
        if parent == dir_p:
            break
        dir_p = parent
    return None


def lockfile_names(root: str | Path) -> tuple[str, ...]:
    """Presence reporting only — does not claim poetry/uv/conda env managers work."""
    root_p = Path(root).expanduser().resolve()
    names: list[str] = []
    for name in ("uv.lock", "poetry.lock", "Pipfile.lock", "environment.yml"):
        if (root_p / name).is_file():
            names.append(name)
    return tuple(names)


def system_python_on_path(*, exclude: Path | None = None) -> Path | None:
    """PATH python/py — never invent Iris product or Agent Core venv as project env."""
    exclude_r = None
    if exclude is not None:
        try:
            exclude_r = Path(exclude).resolve()
        except OSError:
            exclude_r = None
    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if not found:
            continue
        p = Path(found)
        try:
            resolved = p.resolve()
        except OSError:
            continue
        if exclude_r is not None and resolved == exclude_r:
            continue
        if _usable_project_python(resolved) is None:
            continue
        if resolved.is_file():
            return resolved
    return None


def iris_product_python() -> Path | None:
    try:
        return Path(sys.executable).resolve()
    except OSError:
        return None


def agent_core_home() -> Path:
    """Agent Core home — Desktop product and User Workspace stay outside this tree.

    Mirrors ``iris_agent_home`` / ``product_agent_home`` without importing engine.
    """
    override = (os.environ.get("IRIS_AGENT_HOME") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".iris-light" / "agent").resolve()


def _is_product_interpreter(py: Path | None) -> bool:
    """True when py is Iris product sys.executable (never a project env)."""
    if py is None:
        return False
    product = iris_product_python()
    if product is None:
        return False
    try:
        return py.resolve() == product
    except OSError:
        return False


def _is_agent_core_interpreter(py: Path | None) -> bool:
    """True when py lives under Agent Home ``…/venv`` (Iris Agent / Hermes checkout).

    User project runs must not silently inherit this; only explicit user_python may.
    """
    if py is None:
        return False
    try:
        resolved = py.resolve()
        home = agent_core_home()
        rel = resolved.relative_to(home)
    except (ValueError, OSError):
        return False
    return "venv" in {p.lower() for p in rel.parts}


def _usable_project_python(py: Path | None) -> Path | None:
    """Drop Desktop product and Agent Core interpreters from silent discovery."""
    if py is None:
        return None
    if _is_product_interpreter(py) or _is_agent_core_interpreter(py):
        return None
    return py


def active_virtual_env_python() -> Path | None:
    """VIRTUAL_ENV marker → runnable python, else None.

    Skips Iris product VIRTUAL_ENV (pythonw -m iris often sets it to the app venv)
    and Agent Core ``…/agent/*/venv`` (never a user project env unless user_python).
    """
    raw = (os.environ.get("VIRTUAL_ENV") or "").strip()
    if not raw:
        return None
    return _usable_project_python(python_in_prefix(raw))


def active_conda_python() -> Path | None:
    """CONDA_PREFIX marker → runnable python, else None.

    Skips Iris product and Agent Core interpreters.
    """
    raw = (os.environ.get("CONDA_PREFIX") or "").strip()
    if not raw:
        return None
    return _usable_project_python(python_in_prefix(raw))


def _run_capture(argv: list[str], *, cwd: Path | None = None) -> str | None:
    try:
        proc = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            cwd=str(cwd) if cwd is not None else None,
            **no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or "").strip().splitlines()
    return line[0].strip() if line else None


def discover_uv_python(root: str | Path) -> Path | None:
    """uv interpreter only when uv.lock exists AND `uv` binary resolves a runnable python.

    Lockfile presence alone ≠ supported; binary alone without lockfile does not claim uv.
    """
    root_p = Path(root).expanduser().resolve()
    if not (root_p / "uv.lock").is_file():
        return None
    if not shutil.which("uv"):
        return None
    out = _run_capture(["uv", "python", "find"], cwd=root_p)
    if not out:
        return None
    cand = Path(out)
    try:
        cand = cand.resolve()
    except OSError:
        return None
    return cand if cand.is_file() else None


def discover_poetry_python(root: str | Path) -> Path | None:
    """poetry env only when poetry.lock exists AND `poetry` binary resolves an env.

    Lockfile presence alone ≠ supported; binary alone without lockfile does not claim poetry.
    """
    root_p = Path(root).expanduser().resolve()
    if not (root_p / "poetry.lock").is_file():
        return None
    if not shutil.which("poetry"):
        return None
    out = _run_capture(["poetry", "env", "info", "-p"], cwd=root_p)
    if not out:
        return None
    return python_in_prefix(out)


def discover_conda_python(root: str | Path) -> Path | None:
    """conda env only if `conda` binary can resolve — environment.yml alone is not enough."""
    _ = root  # project yml presence is reported via locks, not support
    if not shutil.which("conda"):
        return None
    # Active prefix already handled; project-named env discovery is out of scope (find-only, no create).
    return None


def is_bare_python_launcher(token: str) -> bool:
    """True for bare python/py tokens — not an absolute/relative interpreter path."""
    s = str(token).strip()
    if not s or "/" in s or "\\" in s:
        return False
    return s.lower() in _PYTHON_LAUNCHER_NAMES


def is_python_launcher_token(token: str) -> bool:
    """Basename is a python launcher (may include directory — project.bind uses this)."""
    return Path(str(token)).name.lower() in _PYTHON_LAUNCHER_NAMES


def is_py_version_selector(token: str) -> bool:
    import re

    return bool(re.fullmatch(r"-\d+(\.\d+)?", str(token).strip()))


@dataclass(frozen=True)
class WorkspacePython:
    python: Path | None
    root: Path | None
    source: str  # user|virtual_env|conda|venv|uv|poetry|system|created|none
    locks: tuple[str, ...] = ()


class WorkspaceEnvironmentResolver:
    """Authoritative project interpreter discovery for agent / project.run / process.manage."""

    def resolve(
        self,
        *,
        project_root: str | Path,
        file: str | Path | None = None,
        user_python: str | Path | None = None,
        allow_create: bool = False,
    ) -> WorkspacePython:
        root = Path(project_root).expanduser().resolve()
        locks = lockfile_names(root)

        if user_python:
            up = Path(user_python).expanduser()
            try:
                up_r = up.resolve()
            except OSError:
                up_r = up
            if up_r.is_file():
                return WorkspacePython(python=up_r, root=root, source=_SOURCE_USER, locks=locks)

        # Active shell markers beat unrelated project .venv (priority 2).
        ve_py = active_virtual_env_python()
        if ve_py is not None:
            return WorkspacePython(
                python=ve_py,
                root=root,
                source=_SOURCE_VIRTUAL_ENV,
                locks=locks,
            )
        conda_py = active_conda_python()
        if conda_py is not None:
            return WorkspacePython(
                python=conda_py,
                root=root,
                source=_SOURCE_CONDA,
                locks=locks,
            )

        # Prefer bound root .venv, then walk-up from file (IDE parity).
        # An explicitly bound IRIS project may use its own .venv. Unrelated
        # workspaces must not discover the app interpreter by walking ancestors.
        at_root = find_venv_python(root)
        if at_root is not None and not _is_agent_core_interpreter(at_root):
            return WorkspacePython(python=at_root, root=root, source=_SOURCE_VENV, locks=locks)

        start: Path | None = None
        if file:
            fp = Path(file)
            if not fp.is_absolute():
                fp = root / fp
            start = fp
        else:
            start = root
        walked = walk_up_venv_python(start)
        if walked is not None:
            py, venv_root = walked
            if not _is_agent_core_interpreter(py) and (
                venv_root == root or not _is_product_interpreter(py)
            ):
                return WorkspacePython(
                    python=py, root=venv_root, source=_SOURCE_VENV, locks=locks
                )

        # Tool discovery — runnable binary required; lockfiles already in locks.
        uv_py = discover_uv_python(root)
        if uv_py is not None and not _is_agent_core_interpreter(uv_py):
            return WorkspacePython(python=uv_py, root=root, source=_SOURCE_UV, locks=locks)
        poetry_py = discover_poetry_python(root)
        if poetry_py is not None and not _is_agent_core_interpreter(poetry_py):
            return WorkspacePython(python=poetry_py, root=root, source=_SOURCE_POETRY, locks=locks)
        conda_disc = discover_conda_python(root)
        if conda_disc is not None and not _is_agent_core_interpreter(conda_disc):
            return WorkspacePython(python=conda_disc, root=root, source=_SOURCE_CONDA, locks=locks)

        if allow_create:
            created = self._create_venv(root)
            return WorkspacePython(python=created, root=root, source=_SOURCE_CREATED, locks=locks)

        sys_py = system_python_on_path(exclude=iris_product_python())
        if sys_py is not None:
            return WorkspacePython(python=sys_py, root=root, source=_SOURCE_SYSTEM, locks=locks)

        return WorkspacePython(python=None, root=root, source=_SOURCE_NONE, locks=locks)

    def _create_venv(self, root: Path) -> Path:
        venv_dir = root / ".venv"
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            cwd=str(root),
            **no_window_kwargs(),
        )
        found = find_venv_python(root)
        if found is None:
            raise FileNotFoundError(f"venv created but python missing under {venv_dir}")
        return found


def bind_execution_argv(
    argv: list[str],
    *,
    project_root: str | Path,
    allow_create: bool = False,
    file: str | Path | None = None,
    user_python: str | Path | None = None,
) -> list[str]:
    """Rewrite bare python/py launchers or leading .py file via Resolver.

    Full interpreter paths (e.g. sys.executable) are left alone so Runtime
    tests and explicit paths are not silently remapped. allow_create=False
    on hot paths — never creates .venv here unless caller opts in.
    """
    if not argv:
        return []
    out = [str(x) for x in argv]
    first = out[0]
    resolver = WorkspaceEnvironmentResolver()

    if is_bare_python_launcher(first):
        hit = resolver.resolve(
            project_root=project_root,
            file=file,
            user_python=user_python,
            allow_create=allow_create,
        )
        rest = out[1:]
        if first.lower() in ("py", "py.exe") and rest and is_py_version_selector(rest[0]):
            rest = rest[1:]
        if hit.python is None:
            return [first, *rest]
        return [str(hit.python.resolve()), *rest]

    # Leading script: python file as argv[0] → prepend resolved interpreter.
    script_hint = file
    if Path(first).suffix.lower() == ".py":
        script_hint = script_hint or first
        hit = resolver.resolve(
            project_root=project_root,
            file=script_hint,
            user_python=user_python,
            allow_create=allow_create,
        )
        if hit.python is not None:
            return [str(hit.python.resolve()), *out]
    return out
