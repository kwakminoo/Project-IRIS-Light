"""Qwen 스트림 / custom voice / GPT-SoVITS → PCM16 청크."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

from services.voice_runtime.config import CONFIG
from services.voice_runtime.tts_service import TTS_LANGUAGE, TTSService, _pcm16_bytes

DEFAULT_SAMPLE_RATE = 24000
PCM_YIELD_BYTES = 4096
ENGINES = ("qwen", "qwen_custom", "gpt_sovits")


@dataclass(frozen=True)
class StreamSynthRequest:
    text: str
    engine: str = "qwen"
    voice_prompt_hash: str = ""
    tts_model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    tone: str | None = None
    custom_speaker: str = "iris"
    custom_model_path: str = ""
    gpt_sovits_url: str = "http://127.0.0.1:9880"
    voice_data_dir: str = ""
    tone_routing: bool = True


def faster_qwen_available() -> bool:
    try:
        import faster_qwen3_tts  # noqa: F401
    except Exception:
        return False
    return True


def normalize_engine(engine: str) -> str:
    value = (engine or "qwen").strip().lower()
    return value if value in ENGINES else "qwen"


def custom_speaker_name(base: str, tone: str | None, *, tone_routing: bool) -> str:
    root = (base or "iris").strip() or "iris"
    if tone_routing and (tone or "").strip():
        return f"{root}_{tone.strip()}"
    return root


def iter_pcm_slices(pcm: bytes, chunk_bytes: int = PCM_YIELD_BYTES) -> Iterator[bytes]:
    step = max(2, int(chunk_bytes or PCM_YIELD_BYTES))
    data = pcm or b""
    for i in range(0, len(data), step):
        piece = data[i : i + step]
        if piece:
            yield piece


def sovits_tts_payload(text: str, ref_audio: str, ref_text: str) -> dict[str, Any]:
    return {
        "text": text,
        "text_lang": "ko",
        "ref_audio_path": ref_audio,
        "prompt_text": ref_text or "",
        "prompt_lang": "ko",
        "media_type": "wav",
        "streaming_mode": False,
    }


def resolve_tone_ref_file(source_file: str, voice_data_dir: str) -> str:
    raw = (source_file or "").strip()
    if not raw:
        return ""
    direct = Path(raw)
    if direct.is_file():
        return str(direct)
    root = Path(voice_data_dir) if (voice_data_dir or "").strip() else None
    if root is None:
        return ""
    for cand in (root / raw, root / direct.name):
        if cand.is_file():
            return str(cand)
    return ""


def _load_fast_model(service: TTSService, model_name: str) -> Any | None:
    key = f"fast:{model_name}"
    cached = service._mm.get_tts(key)
    if cached is not None:
        return cached
    try:
        import faster_qwen3_tts as fast_mod  # type: ignore
    except Exception:
        return None
    cls = getattr(fast_mod, "FasterQwen3TTS", None) or getattr(fast_mod, "Qwen3TTS", None)
    if cls is None:
        return None
    try:
        model = cls.from_pretrained(model_name)
    except Exception:
        return None
    service._mm.set_tts(key, model)
    return model


def _pcm_from_audio(audio: Any, sample_rate: int) -> tuple[bytes, int]:
    return _pcm16_bytes(audio), int(sample_rate or DEFAULT_SAMPLE_RATE)


def _iter_stream_call(fn: Any, **kwargs: Any) -> Iterator[tuple[bytes, int]]:
    result = fn(**kwargs)
    if result is None:
        return
    # (wavs, sample_rate) 통짜 반환 vs 청크 generator
    if (
        isinstance(result, (tuple, list))
        and len(result) == 2
        and isinstance(result[1], (int, float))
        and int(result[1]) > 1000
    ):
        wavs, sr = result
        wav = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
        yield _pcm_from_audio(wav, sr)
        return
    if hasattr(result, "__iter__") and not isinstance(result, (bytes, bytearray, str)):
        for item in result:
            audio = item
            sr = DEFAULT_SAMPLE_RATE
            if isinstance(item, (tuple, list)) and item:
                audio = item[0]
                if len(item) > 1 and isinstance(item[1], (int, float)) and int(item[1]) > 1000:
                    sr = int(item[1])
            yield _pcm_from_audio(audio, sr)


def _wav_bytes_to_pcm(blob: bytes) -> tuple[bytes, int]:
    with wave.open(BytesIO(blob), "rb") as wf:
        sr = int(wf.getframerate() or DEFAULT_SAMPLE_RATE)
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if width != 2:
        raise RuntimeError("GPT-SoVITS wav는 16bit PCM이어야 합니다.")
    if channels <= 1:
        return raw, sr
    # 스테오면 왼쪽만. ponytail: 다운믹스 대신 첫 채널.
    frame = channels * 2
    return b"".join(raw[i : i + 2] for i in range(0, len(raw), frame)), sr


def fetch_gpt_sovits_wav(*, base_url: str, text: str, ref_audio: str, ref_text: str) -> bytes:
    root = (base_url or "http://127.0.0.1:9880").rstrip("/")
    payload = json.dumps(sovits_tts_payload(text, ref_audio, ref_text), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8", "Accept": "*/*"}
    errors: list[str] = []
    for url in (f"{root}/tts", root):
        req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120.0) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            errors.append(f"POST {url} HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"POST {url}: {exc}")
            continue
        if body[:4] == b"RIFF":
            return body
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            errors.append(f"POST {url}: wav가 아님")
            continue
        path = str((data or {}).get("path") or (data or {}).get("audio_path") or "")
        if path and Path(path).is_file():
            return Path(path).read_bytes()
        errors.append(f"POST {url}: 경로 없음")
    query = urllib.parse.urlencode(
        {
            "text": text,
            "text_lang": "ko",
            "ref_audio_path": ref_audio,
            "prompt_lang": "ko",
            "prompt_text": ref_text or "",
        }
    )
    get_url = f"{root}/?{query}"
    try:
        with urllib.request.urlopen(get_url, timeout=120.0) as resp:
            body = resp.read()
        if body[:4] == b"RIFF":
            return body
    except Exception as exc:  # noqa: BLE001
        errors.append(f"GET {root}: {exc}")
    raise RuntimeError("GPT-SoVITS 호출 실패. " + " | ".join(errors[-3:]))


def _tone_ref(service: TTSService, tone: str, voice_data_dir: str) -> tuple[str, str]:
    profile = service.profile
    if profile is None:
        return "", ""
    ref = profile.tone_reference(tone)
    if ref is None:
        return "", ""
    path = resolve_tone_ref_file(ref.source_file, voice_data_dir)
    return path, ref.ref_text or ""


def iter_pcm_chunks(service: TTSService, req: StreamSynthRequest) -> Iterator[tuple[bytes, int]]:
    text = (req.text or "").strip()
    if not text:
        raise RuntimeError("TTS 텍스트가 비어 있습니다.")
    if CONFIG.mock_mode:
        pcm, sr = _pcm16_bytes([0.0] * (DEFAULT_SAMPLE_RATE // 5)), DEFAULT_SAMPLE_RATE
        yield pcm, sr
        return

    engine = normalize_engine(req.engine)
    resolved_tone = service.resolve_tone(text, req.tone) if req.tone_routing else (req.tone or "neutral")
    if engine == "gpt_sovits":
        ref_audio, ref_text = _tone_ref(service, resolved_tone, req.voice_data_dir)
        if not ref_audio:
            raise RuntimeError(
                "GPT-SoVITS 참조 음성이 없습니다. 녹음 폴더(voice_data_dir)에 프로필 source_file이 있어야 합니다."
            )
        blob = fetch_gpt_sovits_wav(
            base_url=req.gpt_sovits_url,
            text=text,
            ref_audio=ref_audio,
            ref_text=ref_text,
        )
        pcm, sr = _wav_bytes_to_pcm(blob)
        yield pcm, sr
        return

    if engine == "qwen_custom":
        model_name = (req.custom_model_path or req.tts_model_name).strip()
        model = service._ensure_tts_model(model_name)
        speaker = custom_speaker_name(req.custom_speaker, resolved_tone, tone_routing=req.tone_routing)
        kwargs = {"text": text, "speaker": speaker, "language": TTS_LANGUAGE}
        fn = getattr(model, "generate_custom_voice_streaming", None) or getattr(
            model, "generate_custom_voice", None
        )
        if fn is None:
            raise RuntimeError("이 체크포인트는 generate_custom_voice를 지원하지 않습니다.")
        try:
            yield from _iter_stream_call(fn, **kwargs)
            return
        except Exception:
            if speaker == req.custom_speaker:
                raise
            kwargs["speaker"] = req.custom_speaker or "iris"
            yield from _iter_stream_call(fn, **kwargs)
            return

    # qwen clone — 녹음 wav가 있으면 CUDA graph 스트림, 없으면 저장된 prompt.
    use_profile = service._should_use_profile(req.voice_prompt_hash)
    ref_audio, ref_text = ("", "")
    prepared = None
    if use_profile:
        ref_audio, ref_text = _tone_ref(service, resolved_tone, req.voice_data_dir)
        prepared = service.prepare_profile_prompt(resolved_tone)
    else:
        prepared = service._mm.get_prepared_voice(req.voice_prompt_hash)

    fast = _load_fast_model(service, req.tts_model_name)
    if fast is not None:
        stream_fn = getattr(fast, "generate_voice_clone_streaming", None)
        gen_fn = getattr(fast, "generate_voice_clone", None)
        call = stream_fn or gen_fn
        if call is not None and (ref_audio or prepared is not None):
            kwargs: dict[str, Any] = {"text": text, "language": TTS_LANGUAGE, "chunk_size": 8}
            if ref_audio:
                kwargs["ref_audio"] = ref_audio
                kwargs["ref_text"] = ref_text
            elif prepared is not None:
                kwargs["voice_clone_prompt"] = prepared.voice_clone_prompt
            try:
                yield from _iter_stream_call(call, **kwargs)
                return
            except TypeError:
                kwargs.pop("chunk_size", None)
                try:
                    yield from _iter_stream_call(call, **kwargs)
                    return
                except Exception:
                    pass
            except Exception:
                pass

    if prepared is None or prepared.voice_clone_prompt is None:
        raise RuntimeError("voice clone prompt가 없습니다. 기준 음성을 다시 확정하세요.")
    model = service._ensure_tts_model(req.tts_model_name)
    generate_kwargs: dict[str, Any] = {
        "text": text,
        "language": TTS_LANGUAGE,
        "voice_clone_prompt": prepared.voice_clone_prompt,
    }
    if not use_profile:
        from services.voice_runtime.tts_service import TTS_X_VECTOR_ONLY_MODE

        generate_kwargs["x_vector_only_mode"] = TTS_X_VECTOR_ONLY_MODE
    wavs, sample_rate = model.generate_voice_clone(**generate_kwargs)
    pcm, sr = _pcm_from_audio(wavs[0], sample_rate)
    for piece in iter_pcm_slices(pcm):
        yield piece, sr


def iter_pcm_events(service: TTSService, req: StreamSynthRequest) -> Iterator[dict[str, Any]]:
    started = False
    sr = DEFAULT_SAMPLE_RATE
    engine = normalize_engine(req.engine)
    for pcm, rate in iter_pcm_chunks(service, req):
        sr = int(rate or sr)
        if not started:
            yield {"type": "start", "sample_rate": sr, "engine": engine}
            started = True
        yield {"type": "chunk", "pcm_b64": base64.b64encode(pcm).decode("ascii")}
    if not started:
        yield {"type": "start", "sample_rate": sr, "engine": engine}
    yield {"type": "end", "sample_rate": sr, "engine": engine}
