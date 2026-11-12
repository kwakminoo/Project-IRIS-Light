"""Product UI code should import IrisAgent* worker names, not Hermes* class names.

HermesChatWorker may remain as a compatibility alias in iris_agent_workers.py.
Self-checks under _check_* may still mention Hermes names while migrating.

Run:
  .venv\\Scripts\\python.exe -m iris.ui._check_iris_branding_worker_aliases
"""

from __future__ import annotations

import re
from pathlib import Path

_UI_ROOT = Path(__file__).resolve().parent
_FORBIDDEN_IMPORT = re.compile(
    r"from\s+iris\.ui\.workers(?:\.iris_agent_workers|\.hermes_workers|\.iris_agent_update_worker)?\s+import\s+[^\n]*\bHermes(?:Chat|Health|ControlSync|ModelSync|UpdateCheck|UpdateApply)Worker\b"
)
_FORBIDDEN_BARE = re.compile(
    r"\bHermesChatWorker\b|\bHermesHealthWorker\b|\bHermesUpdateCheckWorker\b|\bHermesUpdateApplyWorker\b"
)


def _product_ui_files() -> list[Path]:
    out: list[Path] = []
    for path in _UI_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        name = path.name
        if name.startswith("_check_") or name == "_check_iris_branding_worker_aliases.py":
            continue
        # Definition + shim modules may still define Hermes* aliases.
        if name in (
            "iris_agent_workers.py",
            "hermes_workers.py",
            "iris_agent_update_worker.py",
        ):
            continue
        out.append(path)
    return out


def find_hermes_worker_imports() -> list[str]:
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
                # Instantiation / type refs in product UI
                if (
                    "HermesChatWorker(" in line
                    or "HermesHealthWorker(" in line
                    or "HermesUpdateCheckWorker(" in line
                    or "HermesUpdateApplyWorker(" in line
                ):
                    hits.append(f"{rel}:{i}:{line.strip()}")
    return hits


def main() -> int:
    hits = find_hermes_worker_imports()
    if hits:
        print("iris_branding_worker_aliases FAIL")
        for h in hits:
            print(h)
        return 1
    print("iris_branding_worker_aliases ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
