"""보이스 프로필로 톤별 샘플 음성을 만들어 귀로 확인한다.

프로필이 제대로 적용됐는지는 결국 들어봐야 안다. 톤마다 대표 문장을 하나씩
합성해서 한 폴더에 모아 둔다.

사용:
    $env:VOICE_RUNTIME_MOCK=0
    .\\.venv-voice\\Scripts\\python.exe scripts\\preview_voice_profile.py
    .\\.venv-voice\\Scripts\\python.exe scripts\\preview_voice_profile.py --tone caution --text "직접 넣은 문장"
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.voice_runtime.config import CONFIG  # noqa: E402
from services.voice_runtime.model_manager import VoiceModelManager  # noqa: E402
from services.voice_runtime.tone_router import (  # noqa: E402
    TONE_BRIEFING,
    TONE_CAUTION,
    TONE_NARRATION,
    TONE_NEUTRAL,
    TONE_NUMERIC,
    TONE_QUESTION,
    TONE_DESCRIPTIONS,
)
from services.voice_runtime.tts_service import TTSService  # noqa: E402

# 톤마다 그 톤이 겨냥한 상황의 문장을 쓴다. 라우팅도 같이 검증된다.
SAMPLE_TEXTS: dict[str, str] = {
    TONE_NEUTRAL: "회의실 예약을 완료했습니다. 필요한 자료는 미리 올려두었습니다.",
    TONE_QUESTION: "지금 바로 보낼까요, 아니면 검토 후에 보낼까요?",
    TONE_BRIEFING: "오늘 확인할 항목은 세 가지입니다. 배포, 로그 점검, 백업입니다.",
    TONE_CAUTION: "이 작업은 파일을 삭제하며 되돌리기 어렵습니다. 확인이 필요합니다.",
    TONE_NUMERIC: "지금은 오전 아홉 시 십이 분이고, 미읽음 메일은 열일곱 통입니다.",
    TONE_NARRATION: (
        "오전 업무 시작을 돕겠습니다. 어제 남은 작업을 먼저 정리했고, "
        "회신이 필요한 메일을 위로 올려두었습니다. 급한 일정은 없으니 "
        "순서대로 진행하시면 됩니다."
    ),
}


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate() or 1
        return handle.getnframes() / float(rate)


def main() -> int:
    parser = argparse.ArgumentParser(description="보이스 프로필 미리듣기")
    parser.add_argument("--tone", default="", help="이 톤만 생성 (기본: 전체)")
    parser.add_argument("--text", default="", help="직접 넣을 문장")
    parser.add_argument("--out", default="", help="출력 폴더 (기본: ~/.iris-light/audio/preview)")
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    if CONFIG.mock_mode:
        print("! VOICE_RUNTIME_MOCK=1 이라 무음이 나옵니다. 0으로 두고 다시 실행하세요.")

    service = TTSService(VoiceModelManager())
    info = service.profile_info()
    if not info.get("available"):
        raise SystemExit(
            "보이스 프로필이 없습니다. scripts/build_voice_profile.py 로 먼저 생성하세요."
        )

    model_name = args.model or str(info.get("model_name") or "")
    out_dir = Path(args.out).expanduser() if args.out else CONFIG.iris_home_dir / "audio" / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"프로필 {info['name']} (dim {info['dim']}, 모델 {model_name})")
    print(f"출력 {out_dir}\n")

    if args.text:
        targets = [(args.tone or "", args.text)]
    elif args.tone:
        if args.tone not in SAMPLE_TEXTS:
            raise SystemExit(f"모르는 톤입니다: {args.tone} (가능: {', '.join(SAMPLE_TEXTS)})")
        targets = [(args.tone, SAMPLE_TEXTS[args.tone])]
    else:
        targets = list(SAMPLE_TEXTS.items())

    failures = 0
    for tone, text in targets:
        started = time.time()
        try:
            result = service.synthesize_speech(
                text=text,
                voice_prompt_hash="",
                tts_model_name=model_name,
                output_dir=out_dir,
                tone=tone or None,
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[{tone or 'auto':10}] 실패: {exc}")
            continue

        elapsed = time.time() - started
        source = Path(result.audio_path)
        # 파일명에 톤을 남겨야 폴더에서 바로 구분된다.
        named = out_dir / f"{result.tone or 'auto'}.wav"
        if source != named:
            named.write_bytes(source.read_bytes())
        duration = wav_duration(named)
        rtf = elapsed / max(duration, 0.01)
        print(f"[{result.tone:10}] {duration:5.1f}s  생성 {elapsed:5.1f}s  RTF {rtf:4.1f}x  -> {named.name}")
        print(f"             {TONE_DESCRIPTIONS.get(result.tone, '')} | {text[:46]}")

    print(f"\n완료. 실패 {failures}건.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
