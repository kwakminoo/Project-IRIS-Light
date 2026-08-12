"""녹음 폴더 → IRIS 보이스 프로필 빌드.

파인튜닝이 아니라 화자 임베딩 추출/집계다. 이 노트북(6GB VRAM)에서는 TTS 파인튜닝이
불가능하고, Qwen3-TTS는 화자 임베딩만으로 음색을 복제하므로 녹음 전체에서 임베딩을
뽑아 이상치를 걸러 평균내는 쪽이 현실적이면서 결과도 안정적이다.

  1) m4a 등 원본 디코딩 → 24kHz mono, 무음 트림, 피크 정규화
  2) faster-whisper로 전사 (파일명은 대본이 아니라 감정/상황 라벨이라 별도 전사 필요)
  3) 파일별 화자 임베딩 추출
  4) 톤별로 묶어 이상치 제거 평균 → 톤 x-vector, 전체 평균 → base x-vector
  5) 톤마다 중심에 가까운 녹음 1개를 ICL 참조로 골라 ref_code/ref_text 저장
  6) iris/assets/voice/ 에 프로필 저장 (녹음 원본 없이도 동작)

사용:
    .\\.venv-voice\\Scripts\\python.exe scripts\\build_voice_profile.py "2차 아이리스 녹음 A-B" "2차 아이리스 녹음 C-H"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.voice_runtime.audio_io import (  # noqa: E402
    TARGET_SAMPLE_RATE,
    decode_audio,
    prepare_for_embedding,
    waveform_metrics,
)
from services.voice_runtime.tone_router import (  # noqa: E402
    is_expressive,
    parse_emotion_label,
    tone_for_recording,
)
from services.voice_runtime.voice_dataset import SUPPORTED_AUDIO_EXTS  # noqa: E402
from services.voice_runtime.voice_profile import (  # noqa: E402
    DEFAULT_PROFILE_MODEL,
    ToneReference,
    VoiceProfile,
    average_embeddings,
    default_profile_paths,
    most_central_index,
)

WHISPER_SAMPLE_RATE = 16000

# ICL 참조로 쓸 녹음 길이. 너무 짧으면 억양 정보가 모자라고,
# 너무 길면 ref_code가 커져서 생성 컨텍스트를 잡아먹는다.
ICL_MIN_DURATION = 4.0
ICL_MAX_DURATION = 14.0


@dataclass
class SampleRecord:
    path: Path
    tone: str
    label: str
    expressive: bool
    duration: float
    peak: float
    rms: float
    silence_ratio: float
    clipping: bool
    transcript: str = ""
    transcript_confidence: float = 0.0
    x_vector: np.ndarray | None = None
    error: str = ""

    @property
    def usable(self) -> bool:
        return not self.error and self.x_vector is not None


@dataclass
class BuildStats:
    total: int = 0
    failed: int = 0
    expressive_excluded: int = 0
    outliers_dropped: int = 0
    per_tone: dict[str, int] = field(default_factory=dict)


def discover(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            raise SystemExit(f"녹음 폴더가 없습니다: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTS:
                found.append(path)
    return found


def load_whisper(model_name: str, device: str):
    from faster_whisper import WhisperModel  # type: ignore

    compute_type = "float16" if device == "cuda" else "int8"
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def transcribe(whisper, samples_24k: np.ndarray, language: str) -> tuple[str, float]:
    """전사문과 신뢰도(평균 로그확률을 0..1로 눌러놓은 값)를 돌려준다."""
    from services.voice_runtime.audio_io import _resample_linear

    audio16 = _resample_linear(samples_24k, TARGET_SAMPLE_RATE, WHISPER_SAMPLE_RATE)
    segments, _info = whisper.transcribe(
        audio16,
        language=language,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    parts: list[str] = []
    logprobs: list[float] = []
    for segment in segments:
        text = (segment.text or "").strip()
        if text:
            parts.append(text)
            logprobs.append(float(segment.avg_logprob))
    transcript = " ".join(parts).strip()
    if not logprobs:
        return transcript, 0.0
    confidence = float(np.exp(np.mean(logprobs)))
    return transcript, max(0.0, min(1.0, confidence))


def load_tts(model_name: str):
    import torch
    from qwen_tts import Qwen3TTSModel  # type: ignore

    if torch.cuda.is_available():
        kwargs = {"device_map": "cuda:0", "dtype": torch.bfloat16}
    else:
        kwargs = {"device_map": "cpu", "dtype": torch.float32}
    return Qwen3TTSModel.from_pretrained(model_name, **kwargs)


def extract_x_vector(tts, samples: np.ndarray) -> np.ndarray:
    """모델의 speaker encoder로 (D,) 임베딩. 입력은 24kHz mono float32."""
    embedding = tts.model.extract_speaker_embedding(
        audio=np.asarray(samples, dtype=np.float32),
        sr=TARGET_SAMPLE_RATE,
    )
    return embedding.detach().float().cpu().numpy().reshape(-1)


def pick_icl_reference(records: list[SampleRecord]) -> SampleRecord | None:
    """톤 안에서 ICL 참조로 쓸 녹음 하나. 길이·전사 신뢰도·중심 근접도를 함께 본다."""
    eligible = [
        r
        for r in records
        if ICL_MIN_DURATION <= r.duration <= ICL_MAX_DURATION
        and r.transcript.strip()
        and r.transcript_confidence >= 0.6
        and not r.clipping
    ]
    if not eligible:
        # 조건을 못 맞추면 전사가 있는 것 중 가장 신뢰도 높은 것으로 완화한다.
        eligible = [r for r in records if r.transcript.strip()]
    if not eligible:
        return None

    centroid_idx = most_central_index([r.x_vector for r in eligible])  # type: ignore[misc]
    centroid = eligible[centroid_idx]

    def score(record: SampleRecord) -> float:
        length_fit = 1.0 - min(1.0, abs(record.duration - 9.0) / 9.0)
        central = 1.0 if record is centroid else 0.0
        return record.transcript_confidence * 0.5 + length_fit * 0.3 + central * 0.2

    return max(eligible, key=score)


def build_ref_code(tts, record: SampleRecord) -> tuple[np.ndarray | None, np.ndarray | None]:
    """대표 녹음에서 ICL용 ref_code를 만든다.

    라이브러리의 create_voice_clone_prompt를 그대로 써서 리샘플/토크나이즈 규칙이
    런타임 생성 경로와 어긋나지 않게 한다.
    """
    decoded = prepare_for_embedding(record.path)
    items = tts.create_voice_clone_prompt(
        ref_audio=[(decoded.samples, decoded.sample_rate)],
        ref_text=[record.transcript],
        x_vector_only_mode=[False],
    )
    item = items[0]
    ref_code = None
    if item.ref_code is not None:
        ref_code = item.ref_code.detach().cpu().numpy().astype(np.int32)
    x_vector = item.ref_spk_embedding.detach().float().cpu().numpy().reshape(-1)
    return ref_code, x_vector


def main() -> int:
    parser = argparse.ArgumentParser(description="IRIS 보이스 프로필 빌드")
    parser.add_argument("roots", nargs="+", help="녹음 폴더 경로")
    parser.add_argument("--tts-model", default=DEFAULT_PROFILE_MODEL)
    parser.add_argument("--whisper-model", default="medium")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--name", default="iris-2nd")
    parser.add_argument("--no-transcript", action="store_true", help="전사 생략 (x-vector 전용 프로필)")
    parser.add_argument("--out-npz", default="", help="기본: iris/assets/voice/iris_voice_profile.npz")
    parser.add_argument("--report", default="", help="샘플별 상세 리포트 jsonl 경로")
    args = parser.parse_args()

    roots = [Path(r).expanduser().resolve() for r in args.roots]
    files = discover(roots)
    if not files:
        raise SystemExit("오디오 파일을 찾지 못했습니다.")
    print(f"[1/5] 녹음 {len(files)}개 발견")

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"      device={device}")

    stats = BuildStats(total=len(files))
    records: list[SampleRecord] = []

    # 6GB VRAM에서는 whisper와 TTS를 동시에 올릴 수 없다.
    # 전사를 전부 끝내고 whisper를 내린 뒤에 TTS를 올린다.
    print("[2/5] 디코딩 · 전사")
    whisper = None if args.no_transcript else load_whisper(args.whisper_model, device)
    started = time.time()
    for index, path in enumerate(files, start=1):
        label = parse_emotion_label(path.stem)
        record = SampleRecord(
            path=path,
            tone=tone_for_recording(path),
            label=label,
            expressive=is_expressive(label) and path.parent.name.upper().startswith("A"),
            duration=0.0,
            peak=0.0,
            rms=0.0,
            silence_ratio=1.0,
            clipping=False,
        )
        try:
            decoded = prepare_for_embedding(path)
            peak, rms, silence_ratio, clipping = waveform_metrics(decoded.samples)
            record.duration = decoded.duration
            record.peak = peak
            record.rms = rms
            record.silence_ratio = silence_ratio
            record.clipping = clipping
            if whisper is not None:
                record.transcript, record.transcript_confidence = transcribe(
                    whisper, decoded.samples, args.language
                )
        except Exception as exc:  # noqa: BLE001
            record.error = f"{type(exc).__name__}: {exc}"
            stats.failed += 1
        records.append(record)
        if index % 20 == 0 or index == len(files):
            print(f"      {index}/{len(files)}  ({time.time() - started:.0f}s)")

    if whisper is not None:
        del whisper
        if device == "cuda":
            torch.cuda.empty_cache()

    print(f"[3/5] TTS 로딩 후 화자 임베딩 추출 ({args.tts_model})")
    tts = load_tts(args.tts_model)
    started = time.time()
    for index, record in enumerate(records, start=1):
        if record.error:
            continue
        try:
            decoded = prepare_for_embedding(record.path)
            record.x_vector = extract_x_vector(tts, decoded.samples)
        except Exception as exc:  # noqa: BLE001
            record.error = f"{type(exc).__name__}: {exc}"
            stats.failed += 1
        if index % 20 == 0 or index == len(records):
            print(f"      {index}/{len(records)}  ({time.time() - started:.0f}s)")

    usable = [r for r in records if r.usable and not r.expressive]
    stats.expressive_excluded = sum(1 for r in records if r.expressive)
    if not usable:
        raise SystemExit("쓸 수 있는 녹음이 없습니다.")

    print(f"[4/5] 집계 — 사용 {len(usable)} / 실패 {stats.failed} / 연기감정 제외 {stats.expressive_excluded}")

    base_vector, kept = average_embeddings([r.x_vector for r in usable])  # type: ignore[misc]
    stats.outliers_dropped = len(usable) - len(kept)

    by_tone: dict[str, list[SampleRecord]] = defaultdict(list)
    for record in usable:
        by_tone[record.tone].append(record)

    tones: dict[str, ToneReference] = {}
    for tone, group in sorted(by_tone.items()):
        tone_vector, tone_kept = average_embeddings([r.x_vector for r in group])  # type: ignore[misc]
        stats.per_tone[tone] = len(group)

        ref_code = None
        ref_text = ""
        source_file = ""
        ref_duration = 0.0
        chosen = pick_icl_reference(group) if not args.no_transcript else None
        if chosen is not None and tts is not None:
            try:
                ref_code, _ = build_ref_code(tts, chosen)
                ref_text = chosen.transcript
                # 녹음 원본은 커밋되지 않으니 출처는 사람이 알아볼 수 있는 상대 경로로만 남긴다.
                try:
                    source_file = chosen.path.relative_to(REPO_ROOT).as_posix()
                except ValueError:
                    source_file = f"{chosen.path.parent.name}/{chosen.path.name}"
                ref_duration = chosen.duration
            except Exception as exc:  # noqa: BLE001
                print(f"      ! {tone} ICL 참조 생성 실패: {exc}")

        tones[tone] = ToneReference(
            tone=tone,
            x_vector=tone_vector,
            ref_code=ref_code,
            ref_text=ref_text,
            source_file=source_file,
            sample_count=len(group),
            ref_duration=ref_duration,
        )
        code_info = f"ref_code {ref_code.shape}" if ref_code is not None else "x-vector 전용"
        print(f"      {tone:10} n={len(group):3} (이상치 -{len(group) - len(tone_kept)})  {code_info}")

    profile = VoiceProfile(
        name=args.name,
        model_name=args.tts_model,
        base_x_vector=base_vector,
        tones=tones,
        meta={
            "source_roots": [str(r.name) for r in roots],
            "sample_total": stats.total,
            "sample_used": len(usable),
            "failed": stats.failed,
            "expressive_excluded": stats.expressive_excluded,
            "outliers_dropped": stats.outliers_dropped,
            "whisper_model": "" if args.no_transcript else args.whisper_model,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )

    npz_path = Path(args.out_npz).expanduser() if args.out_npz else default_profile_paths()[0]
    json_path = npz_path.with_suffix(".json")
    profile.save(npz_path, json_path=json_path)
    print(f"[5/5] 저장 완료")
    print(f"      {npz_path}  ({npz_path.stat().st_size / 1024:.0f} KB)")
    print(f"      {json_path}")

    if args.report:
        report_path = Path(args.report).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(
                    json.dumps(
                        {
                            "file": str(record.path),
                            "tone": record.tone,
                            "label": record.label,
                            "expressive": record.expressive,
                            "duration": round(record.duration, 3),
                            "peak": round(record.peak, 4),
                            "rms": round(record.rms, 5),
                            "silence_ratio": round(record.silence_ratio, 4),
                            "clipping": record.clipping,
                            "transcript": record.transcript,
                            "transcript_confidence": round(record.transcript_confidence, 4),
                            "error": record.error,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(f"      리포트: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
