"""마이크 끄기 후 늦은 STT 콜백이 듣기 UI를 다시 켜지 않는지 검사.

  py -3 -m iris.ui._check_mic_listen_stop
"""

from __future__ import annotations


def should_apply_stt_ui(
    *,
    mic_listen_active: bool,
    stt_session: int,
    callback_session: int,
    keep_listening: bool,
) -> bool:
    """MainWindow._on_stt_* 가드와 동일 조건."""
    if callback_session != stt_session:
        return False
    if keep_listening and not mic_listen_active:
        return False
    return True


def should_start_transcribe(*, mic_listen_active: bool, keep_listening: bool) -> bool:
    if keep_listening and not mic_listen_active:
        return False
    return True


def main() -> int:
    # 끄기(session bump) 후 이전 워커 콜백 → 무시
    assert (
        should_apply_stt_ui(
            mic_listen_active=False,
            stt_session=1,
            callback_session=0,
            keep_listening=True,
        )
        is False
    )
    # 켜진 상태 + 같은 세션 → 적용
    assert (
        should_apply_stt_ui(
            mic_listen_active=True,
            stt_session=1,
            callback_session=1,
            keep_listening=True,
        )
        is True
    )
    # 세션은 같지만 이미 끔 → 무시
    assert (
        should_apply_stt_ui(
            mic_listen_active=False,
            stt_session=1,
            callback_session=1,
            keep_listening=True,
        )
        is False
    )
    # 전사 진입 직전 끔
    assert should_start_transcribe(mic_listen_active=False, keep_listening=True) is False
    assert should_start_transcribe(mic_listen_active=True, keep_listening=True) is True
    print("mic_listen_stop check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
