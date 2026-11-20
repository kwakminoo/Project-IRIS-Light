"""Product UI and worker modules must use IrisAgent* names only.

Hermes*Worker compatibility aliases are deleted. Definition modules must not
reintroduce ``HermesChatWorker = …`` style shims.

Run:
  .venv\\Scripts\\python.exe -m iris.ui._check_iris_branding_worker_aliases
"""

from __future__ import annotations

import re
from pathlib import Path

_UI_ROOT = Path(__file__).resolve().parent
_WORKERS = _UI_ROOT / "workers"
_FORBIDDEN_IMPORT = re.compile(
    r"from\s+iris\.ui\.workers(?:\.iris_agent_workers|\.iris_agent_update_worker)?\s+import\s+[^\n]*\bHermes(?:Chat|Health|ControlSync|ModelSync|UpdateCheck|UpdateApply)Worker\b"
)
_FORBIDDEN_BARE = re.compile(
    r"\bHermes(?:Chat|Health|ControlSync|ModelSync|UpdateCheck|UpdateApply)Worker\b"
)
_WORKER_MODULES = (
    _WORKERS / "iris_agent_workers.py",
    _WORKERS / "iris_agent_update_worker.py",
)


def _product_ui_files() -> list[Path]:
    out: list[Path] = []
    for path in _UI_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        name = path.name
        if name.startswith("_check_") or name == "_check_iris_branding_worker_aliases.py":
            continue
        out.append(path)
    return out


def find_agent_worker_imports() -> list[str]:
    hits: list[str] = []
    for path in _product_ui_files():
        rel = path.relative_to(_UI_ROOT.parent.parent)
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _FORBIDDEN_IMPORT.search(line) or (
                _FORBIDDEN_BARE.search(line) and "import" in line
            ):
                hits.append(f"{rel}:{i}:{line.strip()}")
            elif _FORBIDDEN_BARE.search(line) and "IrisAgent" not in line:
                if (
                    "HermesChatWorker(" in line
                    or "HermesHealthWorker(" in line
                    or "HermesControlSyncWorker(" in line
                    or "HermesModelSyncWorker(" in line
                    or "HermesUpdateCheckWorker(" in line
                    or "HermesUpdateApplyWorker(" in line
                ):
                    hits.append(f"{rel}:{i}:{line.strip()}")
    return hits


_ALIAS_BINDING = re.compile(
    r"\bHermes(?:Chat|Health|ControlSync|ModelSync|UpdateCheck|UpdateApply)Worker\s*="
)
_ALIAS_IN_ALL = re.compile(
    r'["\']Hermes(?:Chat|Health|ControlSync|ModelSync|UpdateCheck|UpdateApply)Worker["\']'
)


def find_agent_worker_aliases_in_defs() -> list[str]:
    hits: list[str] = []
    for path in _WORKER_MODULES:
        if not path.is_file():
            hits.append(f"missing:{path.as_posix()}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(_UI_ROOT.parent.parent)
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _ALIAS_BINDING.search(line) or _ALIAS_IN_ALL.search(line):
                hits.append(f"{rel}:{i}:{line.strip()}")
    return hits


def main() -> int:
    hits = find_agent_worker_imports() + find_agent_worker_aliases_in_defs()
    if hits:
        print("iris_branding_worker_aliases FAIL")
        for h in hits:
            print(h)
        return 1
    print("iris_branding_worker_aliases ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
