"""_finish_staged_install applies Iris Agent baseline overlays before uv sync.

Editable metadata (packages.find + CLI shims) must exist when uv/pip builds
the environment. engine-uv-probe-boost forbids pip install -e after uv sync
success, so overlays cannot wait until after probe.

Run:
  .venv\\Scripts\\python.exe -m iris.system._check_iris_agent_install_overlay_before_sync
"""

from __future__ import annotations

import inspect

from iris.system import iris_agent_install as m


def _check_overlay_before_uv_sync() -> None:
    src = inspect.getsource(m._finish_staged_install)
    overlay_hits = [
        i
        for needle in ("_guard_installed_agent(", "apply_iris_agent_baseline_overlays(")
        if (i := src.find(needle)) >= 0
    ]
    assert overlay_hits, "overlay/_guard missing from _finish_staged_install"
    overlay_pos = min(overlay_hits)
    sync_pos = src.find("uv sync")
    assert sync_pos >= 0, "uv sync marker missing from _finish_staged_install"
    assert overlay_pos < sync_pos, (
        f"overlay at {overlay_pos} must precede uv sync at {sync_pos}"
    )


def _check_no_pip_editable_after_uv_installed_true() -> None:
    """uv sync success (installed=True) must not fall into a new pip install -e."""
    src = inspect.getsource(m._finish_staged_install)
    # After installed = proc.returncode == 0, boost-only recovery — no pip -e.
    marker = "installed = proc.returncode == 0"
    idx = src.find(marker)
    assert idx >= 0, "uv installed assignment missing"
    after = src[idx:]
    # The installed=True recovery path uses _boost_probe_deps; pip -e only under `if not installed`.
    boost_idx = after.find("_boost_probe_deps")
    assert boost_idx >= 0, "probe-boost recovery missing after uv installed"
    # Between installed=True assignment and the next `if not installed:` pip block,
    # there must be no pip install -e call (soft: no `-e` in that window before boost).
    not_installed = after.find("if not installed:")
    window = after[:not_installed] if not_installed >= 0 else after[:boost_idx]
    assert "pip" not in window or "-e" not in window, (
        "pip install -e appears on installed=True path before fallback"
    )


def main() -> None:
    _check_overlay_before_uv_sync()
    _check_no_pip_editable_after_uv_installed_true()
    print("ok")


if __name__ == "__main__":
    main()
