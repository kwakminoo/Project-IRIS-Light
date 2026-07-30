"""SettingsDialog가 쓰는 Qt-비의존 로직 (음성 런타임 호출, 프로필 검증).

QWidget을 import하지 않는다 — 실패 시 ValueError/VoiceRuntimeError를 던지고,
사용자에게 보여줄 메시지는 예외 메시지 그대로 쓴다. QMessageBox 표시는 View(다이얼로그) 책임.
"""

from __future__ import annotations

from pathlib import Path

from iris.audio.voice_runtime_client import VoiceRuntimeClient
from iris.storage.user_profile import UserProfile
from iris.storage.voice_prefs import VoicePreferences


def confirm_voice_reference(base_url: str, prefs: VoicePreferences) -> str:
    """참고 음성/대본을 기준 음성으로 확정하고 voice_prompt_hash를 반환한다."""
    if not prefs.tts_reference_audio or not Path(prefs.tts_reference_audio).is_file():
        raise ValueError("유효한 참고 음성 파일이 필요합니다.")
    if not prefs.tts_reference_text.strip():
        raise ValueError("참고 대본을 입력/수정한 뒤 확정하세요.")
    client = VoiceRuntimeClient(base_url=base_url)
    voice_hash = client.voice_prepare(
        ref_audio_path=prefs.tts_reference_audio,
        ref_text=prefs.tts_reference_text,
        tts_model_name=prefs.tts_model,
    )
    client.voice_set_reference(
        ref_audio_path=prefs.tts_reference_audio,
        ref_text=prefs.tts_reference_text,
        voice_prompt_hash=voice_hash,
    )
    return voice_hash


def ensure_voice_hash_for_test(base_url: str, prefs: VoicePreferences) -> str:
    """테스트 음성 생성 전에 필요한 voice_prompt_hash를 확보한다 (있으면 재사용)."""
    if not prefs.tts_reference_audio or not prefs.tts_reference_text:
        raise ValueError("기준 음성/대본을 먼저 확정하세요.")
    if not Path(prefs.tts_reference_audio).is_file():
        raise ValueError("기준 음성 파일이 없습니다.")
    if prefs.tts_voice_prompt_hash:
        return prefs.tts_voice_prompt_hash
    client = VoiceRuntimeClient(base_url=base_url)
    return client.voice_prepare(
        ref_audio_path=prefs.tts_reference_audio,
        ref_text=prefs.tts_reference_text,
        tts_model_name=prefs.tts_model,
    )


def load_hermes_sync_status_text() -> str:
    """마지막 Iris↔Hermes Control 동기화 상태 문구를 읽는다."""
    try:
        import json

        from iris.system.hermes_iris_control_sync import sync_state_path

        path = sync_state_path()
        if not path.is_file():
            return "상태: 아직 동기화하지 않음"
        data = json.loads(path.read_text(encoding="utf-8"))
        ok = bool(data.get("ok"))
        summary = data.get("messages") or []
        line = (summary[0] if summary else "") or ("동기화됨" if ok else "동기화 이슈")
        return f"상태: {'OK' if ok else '이슈'} — {line}"
    except Exception:  # noqa: BLE001
        return "상태: 아직 동기화하지 않음"


def build_profile_update(
    base: UserProfile,
    *,
    preferred_ide: str,
    ide_exe_path: str,
    ide_cli_path: str,
    project_root: str,
    parents_customized: bool,
    project_parents: list[str],
) -> UserProfile:
    """검증 후 저장할 UserProfile을 만든다. 실패 시 사용자에게 보여줄 메시지의 ValueError."""
    if preferred_ide == "custom" and not ide_exe_path:
        raise ValueError("사용자 지정 IDE는 실행 파일 선택이 필요합니다.")
    data = {
        "name": base.name,
        "occupation": base.occupation,
        "hobbies": base.hobbies,
        "interests": base.interests,
        "work_tasks": base.work_tasks,
        "age": base.age,
        "gender": base.gender,
        "residence": base.residence,
        "contact": base.contact,
        "email": base.email,
        "preferred_ide": preferred_ide or "cursor",
        "ide_exe_path": ide_exe_path if preferred_ide == "custom" else "",
        # ponytail: UI에서 제거 — 기존 값 유지 (필요 시 코드/DB에서만)
        "ide_cli_path": ide_cli_path,
        "project_root": project_root,
        "project_parents": project_parents if parents_customized else [],
    }
    if parents_customized and not data["project_parents"]:
        raise ValueError("부모 폴더가 비어 있습니다. 폴더를 추가하거나 기본값 복원을 누르세요.")
    for raw in data["project_parents"]:
        if not Path(raw).expanduser().is_dir():
            raise ValueError(f"존재하지 않는 폴더입니다:\n{raw}")
    return UserProfile(**data)
