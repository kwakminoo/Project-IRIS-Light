from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.voice_runtime.config import CONFIG


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reviewed IRIS voice items for future Qwen finetuning")
    parser.add_argument("--manifest", default=str(CONFIG.voice_manifest_jsonl))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser()
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    if manifest_path.is_file():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("reviewed") and item.get("transcript"):
                rows.append(
                    {
                        "audio": item.get("audio_path", ""),
                        "text": item.get("transcript", ""),
                        "language": item.get("language", "ko"),
                    }
                )

    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"exported={len(rows)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

