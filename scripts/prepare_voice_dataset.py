from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.voice_runtime.config import CONFIG
from services.voice_runtime.voice_dataset import analyze_folder


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare IRIS voice dataset manifest")
    parser.add_argument("root", help="voice recording root directory")
    parser.add_argument(
        "--no-transcript",
        action="store_true",
        help="skip faster-whisper transcription (metadata/quality only)",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"folder not found: {root}")
        return 1

    transcribe_fn = None
    if not args.no_transcript:
        try:
            from services.voice_runtime.model_manager import VoiceModelManager
            from services.voice_runtime.stt_service import STTService

            stt = STTService(VoiceModelManager())

            def _transcribe(path: Path) -> dict:
                res = stt.transcribe_file(path)
                return {
                    "text": res.text,
                    "language": res.language,
                    "language_probability": res.language_probability,
                }

            transcribe_fn = _transcribe
        except Exception as exc:  # noqa: BLE001
            print(f"transcript disabled: {exc}")

    samples, picks = analyze_folder(
        root,
        jsonl_path=CONFIG.voice_manifest_jsonl,
        csv_path=CONFIG.voice_manifest_csv,
        transcribe_fn=transcribe_fn,
    )
    print(
        f"analyzed={len(samples)} recommended={len(picks)} "
        f"jsonl={CONFIG.voice_manifest_jsonl} csv={CONFIG.voice_manifest_csv}"
    )
    for i, item in enumerate(picks, 1):
        print(f"  #{i} score={item.quality_score} dur={item.duration:.1f}s {item.file_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
