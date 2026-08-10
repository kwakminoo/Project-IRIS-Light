"""IRIS 자동화/학습 권한 레벨."""

from __future__ import annotations

from dataclasses import dataclass

from iris.storage.learning_prefs import PERMISSION_LEVELS


@dataclass(frozen=True)
class PermissionPolicy:
    level: str
    record_keyboard: bool
    record_mouse: bool
    record_screen: bool
    store_key_chars: bool
    prefer_elevation: bool
    executor_confirm_required: bool
    allow_unrestricted_os_control: bool
    label_ko: str
    description_ko: str


_POLICIES: dict[str, PermissionPolicy] = {
    "low": PermissionPolicy(
        level="low",
        record_keyboard=False,
        record_mouse=True,
        record_screen=True,
        store_key_chars=False,
        prefer_elevation=False,
        executor_confirm_required=True,
        allow_unrestricted_os_control=False,
        label_ko="낮은 권한",
        description_ko="화면·마우스만 관찰. 키보드 문자는 저장하지 않습니다.",
    ),
    "normal": PermissionPolicy(
        level="normal",
        record_keyboard=True,
        record_mouse=True,
        record_screen=True,
        store_key_chars=True,
        prefer_elevation=False,
        executor_confirm_required=True,
        allow_unrestricted_os_control=False,
        label_ko="보통 권한",
        description_ko="화면·마우스·키보드를 관찰합니다(비밀번호 필드는 마스킹).",
    ),
    "high": PermissionPolicy(
        level="high",
        record_keyboard=True,
        record_mouse=True,
        record_screen=True,
        store_key_chars=True,
        prefer_elevation=True,
        executor_confirm_required=True,
        allow_unrestricted_os_control=False,
        label_ko="높은 권한",
        description_ko="관찰 + 가능하면 관리자 무결성으로 훅/자동화를 맞춥니다.",
    ),
    "unrestricted": PermissionPolicy(
        level="unrestricted",
        record_keyboard=True,
        record_mouse=True,
        record_screen=True,
        store_key_chars=True,
        prefer_elevation=True,
        executor_confirm_required=False,
        allow_unrestricted_os_control=True,
        label_ko="제한 없음",
        description_ko=(
            "IRIS가 PC 입력·창·프로세스를 제한 없이 조작할 수 있습니다. "
            "실행 확인을 생략하며, 관리자 권한 상승을 요청할 수 있습니다. "
            "비밀번호 필드 저장 마스킹은 유지됩니다."
        ),
    ),
}


def policy_for(level: str) -> PermissionPolicy:
    key = (level or "normal").strip().lower()
    if key not in _POLICIES:
        key = "normal"
    return _POLICIES[key]


def level_choices() -> list[tuple[str, str]]:
    return [(k, _POLICIES[k].label_ko) for k in PERMISSION_LEVELS]


def is_process_elevated() -> bool:
    if sys_platform_win():
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    return False


def sys_platform_win() -> bool:
    import sys

    return sys.platform == "win32"


def request_elevation_hint() -> str:
    if is_process_elevated():
        return "이미 관리자 권한으로 실행 중입니다."
    return (
        "관리자 권한이 필요합니다. Iris Light를 ‘관리자 권한으로 실행’한 뒤 "
        "대상 앱과 동일한 권한 수준에서 학습하세요."
    )
