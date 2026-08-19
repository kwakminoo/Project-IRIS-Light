"""녹음 매니페스트 → Qwen3-TTS SFT JSONL.

학습은 공식 스크립트가 한다. 이 파일은 jsonl만 만든다.

  python scripts/prepare_qwen_sft_jsonl.py "아이리스 녹음" -o train_raw.jsonl --speaker iris

  python Qwen3-TTS/finetuning/prepare_data.py --input_jsonl train_raw.jsonl --output_jsonl train_with_codes.jsonl ...
  python Qwen3-TTS/finetuning/sft_12hz.py --init_model_path Qwen/Qwen3-TTS-12Hz-0.6B-Base --speaker_name iris ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.voice_runtime.config import CONFIG
from services.voice_runtime.tone_router import tone_for_recording
from services.voice_runtime.voice_dataset import load_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Qwen3-TTS SFT jsonl from IRIS recordings")
    parser.add_argument("root", nargs="?", default="", help="recording root (tone folders)")
    parser.add_argument("-o", "--output", default="train_raw.jsonl")
    parser.add_argument("--speaker", default="iris")
    parser.add_argument("--tone-speakers", action="store_true", help="speaker = {base}_{tone}")
    parser.add_argument("--manifest", default="", help="override manifest.jsonl path")
    args = parser.parse_args()

    manifest = Path(args.manifest) if args.manifest else CONFIG.voice_manifest_jsonl
    samples = load_manifest(manifest) if manifest.is_file() else []
    root = Path(args.root).expanduser() if args.root else None
    rows: list[dict[str, str]] = []
    for sample in samples:
        text = (sample.transcript or "").strip()
        audio = Path(sample.audio_path)
        if not text or not audio.is_file():
            continue
        if root is not None and root.is_dir():
            try:
                audio.resolve().relative_to(root.resolve())
            except ValueError:
                continue
        tone = tone_for_recording(audio, root=root)
        speaker = f"{args.speaker}_{tone}" if args.tone_speakers else args.speaker
        rows.append(
            {
                "audio": str(audio),
                "text": text,
                "ref_audio": str(audio),
                "speaker": speaker,
            }
        )
    if not rows:
        print(f"no transcribed samples in {manifest}")
        print("먼저 scripts/prepare_voice_dataset.py 로 전사를 만드세요.")
        return 1

    out = Path(args.output)
    out.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    speakers = sorted({row["speaker"] for row in rows})
    print(f"wrote {len(rows)} lines -> {out}")
    print(f"speakers: {', '.join(speakers)}")
    print("next: Qwen3-TTS/finetuning/prepare_data.py then sft_12hz.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
