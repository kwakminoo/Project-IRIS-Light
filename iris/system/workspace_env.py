"""Workspace Environment Manager — find existing project interpreters; create only when approved.

Priority (resolve):
  1. user-selected interpreter path
  2. existing project .venv (root, then walk-up from file — match IDE)
  3. system python on PATH (not Iris product venv)
  4. create project .venv only if allow_create=True
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


def venv_python_at(root: Path) -> Path:
    root = Path(root)
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


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
    """Presence reporting only — does not claim poetry/uv env managers work."""
    root_p = Path(root).expanduser().resolve()
    names: list[str] = []
    for name in ("uv.lock", "poetry.lock", "Pipfile.lock", "environment.yml"):
        if (root_p / name).is_file():
            names.append(name)
    return tuple(names)


def system_python_on_path(*, exclude: Path | None = None) -> Path | None:
    """PATH python/py — never invent Iris product sys.executable as project env."""
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
        if resolved.is_file():
            return resolved
    return None


def iris_product_python() -> Path | None:
    try:
        return Path(sys.executable).resolve()
    except OSError:
        return None


@dataclass(frozen=True)
class WorkspacePython:
    python: Path | None
    root: Path | None
    source: str  # user | venv | system | created | none
    locks: tuple[str, ...] = ()


class WorkspaceEnvironmentResolver:
    """Authoritative project interpreter discovery for agent / project.run."""

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
                return WorkspacePython(python=up_r, root=root, source="user", locks=locks)

        # Prefer bound root .venv, then walk-up from file (IDE parity).
        at_root = find_venv_python(root)
        if at_root is not None:
            return WorkspacePython(python=at_root, root=root, source="venv", locks=locks)

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
            return WorkspacePython(python=py, root=venv_root, source="venv", locks=locks)

        if allow_create:
            created = self._create_venv(root)
            return WorkspacePython(python=created, root=root, source="created", locks=locks)

        sys_py = system_python_on_path(exclude=iris_product_python())
        if sys_py is not None:
            return WorkspacePython(python=sys_py, root=root, source="system", locks=locks)

        return WorkspacePython(python=None, root=root, source="none", locks=locks)

    def _create_venv(self, root: Path) -> Path:
        import subprocess

        from iris.system.win_subprocess import no_window_kwargs

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
