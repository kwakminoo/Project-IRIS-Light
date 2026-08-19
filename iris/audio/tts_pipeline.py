"""TTS 세그먼트 파이프라이닝 — 다음 합성을 지금 시작해도 되는지 판단.

재생 중인 세그먼트가 끝나기 전에 다음 세그먼트를 미리 합성해 두면 문장
사이 공백이 줄어든다. 단, 앞서 합성해 두는 정도는 1개로 제한한다 — 이미
합성이 끝나 재생을 기다리는 세그먼트(ready)가 있으면 그 이상은 합성하지
않는다.
"""

from __future__ import annotations


def should_start_tts_synth(
    *, synthesizing: bool, pending_count: int, ready_count: int
) -> bool:
    """다음 TTS 세그먼트 합성을 지금 시작해도 되는지.

    - synthesizing: 이미 합성 워커가 돌고 있으면 또 시작하지 않는다.
    - pending_count: 합성 대기 중인 텍스트가 없으면(<=0) 시작할 게 없다.
    - ready_count: 합성은 됐지만 아직 재생 안 된 세그먼트가 이미 있으면
      (>=1) 한 개 앞서가는 것으로 충분 — 더 쌓지 않는다.
    """
    if synthesizing:
        return False
    if pending_count <= 0:
        return False
    if ready_count >= 1:
        return False
    return True
