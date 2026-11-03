"""로그온 시 Hermes gateway만 미리 켠다. Qt·Iris 창 없음.

Windows 작업 스케줄러가 `pythonw` 로 직접 실행한다(`-m` 아님).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

EXIT_OK = 0
EXIT_ERROR = 1


def _install_no_console() -> None:
    try:
        from iris.system.win_subprocess import (
            install_no_console_subprocess_patch,
            suppress_platform_ver_console,
        )

        suppress_platform_ver_console()
        install_no_console_subprocess_patch()
    except Exception:
        pass


def _log_line(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
    try:
        log_dir = Path.home() / ".iris-light" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "hermes_login_warm.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    try:
        print(message, flush=True)
    except Exception:
        pass


def main() -> int:
    _install_no_console()
    try:
        from iris.config.settings import load_settings
        from iris.infrastructure.agent_runtime import ensure_iris_agent_runtime

        settings = load_settings()
        # Supervisor entry (Phase 4b). Lifetime: keep-background — warm may
        # leave gateway running without an Iris window.
        result = ensure_iris_agent_runtime(
            settings.hermes_base_url,
            api_key=settings.hermes_api_key,
            command=settings.hermes_command,
        )
        ok = result.ok
    except Exception as exc:  # noqa: BLE001
        _log_line(f"fail: {exc}")
        return EXIT_ERROR
    if ok:
        _log_line("ok: gateway up")
        return EXIT_OK
    _log_line("fail: ensure_iris_agent_runtime returned not ok")
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
