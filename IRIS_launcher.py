"""PyInstaller 진입점 — IRIS.exe.

저장소에 .venv 가 있으면 구버전 frozen 바이너리 대신
최신 소스(`python -m iris`)로 넘겨 로컬 수정이 즉시 반영되게 한다.
패키지 EXE만 쓰려면 환경변수 IRIS_FORCE_FROZEN=1.
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from iris.system.source_launch import reexec_to_source_if_available

        if reexec_to_source_if_available():
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        # hop 실패 시 frozen 본체로 계속
        pass

    from iris.__main__ import main as iris_main

    iris_main()


if __name__ == "__main__":
    main()
