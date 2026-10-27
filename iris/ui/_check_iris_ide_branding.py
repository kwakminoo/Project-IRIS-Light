"""Phase5: 일상 UI 사용자 카피에 Theia 제품 노출 0 (NOTICE/LICENSE·식별자 제외).

실행: .venv\\Scripts\\python.exe -m iris.ui._check_iris_ide_branding

제외: LICENSE.md / THIRD_PARTY_NOTICES.md, @theia import, load_theia 등 심볼,
개발자 주석·docstring, 설치 로그 상세의 소문자 theia build 진행 줄.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

USER_COPY_FILES = (
    "iris/ui/settings/iris_ide_settings.py",
    "iris/ui/workspaces/iris_ide_window.py",
    "iris/ui/settings/settings_dialog.py",
    "iris/ui/window/main_window.py",
    "iris/ui/control_actions/ide.py",
    "iris/ui/control_actions/project.py",
    "iris/system/setup_protocol.py",
    "iris/system/iris_ide_runtime.py",
)

# 로딩·설정·토스트·설치 안내에 남아 있으면 안 되는 사용자 카피.
BANNED = (
    # "Eclipse Theia" 는 LICENSE/NOTICE·모듈 docstring 엔진 설명에 남을 수 있음.
    # 아래는 설정·로딩·토스트 등 일상 UI에만 금지.
    "Eclipse Theia 기반",
    "Theia URL",
    "Theia 빌드",
    "theia build 순",
    "yarn · tsc · theia",
    "WebEngine/Theia",
    "IRIS IDE (Theia)",
    "IRIS IDE(Theia)",
    "Node·Theia",
    "Theia를 준비",
    "Theia 1.74",
    "Theia runtime health",
    "Theia health check",
    "Theia process exited",
    "Theia ready",
    "Theia health timeout",
    "Theia build output",
    "theia CLI missing",
    "IDE Companion: IRIS IDE (Theia)",
)


def main() -> None:
    license_md = (ROOT / "LICENSE.md").read_text(encoding="utf-8")
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Eclipse Theia" in license_md, "LICENSE.md §6 Theia 고지 유지"
    assert "Eclipse Theia" in notices, "THIRD_PARTY_NOTICES Theia 고지 유지"

    from iris.ui.workspaces.iris_ide_window import IRIS_IDE_TITLE

    assert IRIS_IDE_TITLE == "IRIS IDE"

    pkg = (ROOT / "integrations/iris-ide/package.json").read_text(encoding="utf-8")
    assert '"applicationName": "IRIS IDE"' in pkg

    hits: list[str] = []
    for rel in USER_COPY_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for banned in BANNED:
            if banned in text:
                hits.append(f"{rel}: {banned!r}")

    assert not hits, "user-facing Theia copy:\n  " + "\n  ".join(hits)
    print("iris_ide_branding check ok")


if __name__ == "__main__":
    main()
