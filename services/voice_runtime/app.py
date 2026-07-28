from __future__ import annotations

import json
import os
import signal
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import CONFIG
from .model_manager import VoiceModelManager
from .stt_service import STTService
from .tts_service import TTSService, clear_generated_audio_cache
from .voice_dataset import analyze_folder, load_manifest, recommend_reference_samples


app = FastAPI(title="Iris Light Voice Runtime")
model_manager = VoiceModelManager()
stt_service = STTService(model_manager)
tts_service = TTSService(model_manager)

_shutdown_lock = threading.RLock()
_should_exit = False


class HealthResponse(BaseModel):
    status: str
    pid: int
    mock_mode: bool


@app.get("/health", response_model=HealthResponse)
def health() -> Any:
    return HealthResponse(
        status="ok",
        pid=os.getpid(),
        mock_mode=CONFIG.mock_mode,
    )


class TranscribeRequest(BaseModel):
    audio_b64: str = Field(..., description="wav pcm16 bytes encoded as base64")
    filename_hint: str = "audio.wav"
    model_name: str = "small"
    language: str = "ko"
    vad_filter: bool = True
    beam_size: int = 5
    condition_on_previous_text: bool = False
    compute_type: str | None = None


class TranscribeResponse(BaseModel):
    text: str
    language: str
    language_probability: float


@app.post("/v1/audio/transcriptions", response_model=TranscribeResponse)
def transcribe(req: TranscribeRequest) -> Any:
    try:
        res = stt_service.transcribe_b64(
            req.audio_b64,
            filename_hint=req.filename_hint,
            model_name=req.model_name,
            language=req.language,
            vad_filter=req.vad_filter,
            beam_size=req.beam_size,
            condition_on_previous_text=req.condition_on_previous_text,
            compute_type=req.compute_type,
        )
        return TranscribeResponse(
            text=res.text,
            language=res.language,
            language_probability=res.language_probability,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


class VoicePrepareRequest(BaseModel):
    ref_audio_path: str
    ref_text: str
    tts_model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    voice_prompt_hash: str | None = None


class VoicePrepareResponse(BaseModel):
    voice_prompt_hash: str


@app.post("/v1/voice/prepare", response_model=VoicePrepareResponse)
def voice_prepare(req: VoicePrepareRequest) -> Any:
    try:
        prepared = tts_service.prepare_voice_clone_prompt(
            ref_audio_path=req.ref_audio_path,
            ref_text=req.ref_text,
            tts_model_name=req.tts_model_name,
            voice_prompt_hash=req.voice_prompt_hash,
        )
        return VoicePrepareResponse(voice_prompt_hash=prepared.voice_prompt_hash)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


class SpeechRequest(BaseModel):
    text: str
    voice_prompt_hash: str
    tts_model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"


class SpeechResponse(BaseModel):
    audio_path: str
    text: str


@app.post("/v1/audio/speech", response_model=SpeechResponse)
def speech(req: SpeechRequest) -> Any:
    try:
        out_dir = CONFIG.iris_home_dir / "audio" / "generated"
        result = tts_service.synthesize_speech(
            text=req.text,
            voice_prompt_hash=req.voice_prompt_hash,
            tts_model_name=req.tts_model_name,
            output_dir=out_dir,
        )
        return SpeechResponse(audio_path=result.audio_path, text=result.text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


class VoiceAnalyzeRequest(BaseModel):
    root: str
    with_transcript: bool = True
    stt_model_name: str = "small"
    language: str = "ko"


@app.post("/v1/voice/analyze")
def voice_analyze(req: VoiceAnalyzeRequest) -> Any:
    root = Path(req.root).expanduser()
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"녹음 폴더가 없습니다: {root}")

    def _transcribe(path: Path) -> dict[str, Any]:
        if not req.with_transcript:
            return {"text": "", "language": "ko", "language_probability": 0.0}
        try:
            res = stt_service.transcribe_file(
                path,
                model_name=req.stt_model_name,
                language=req.language,
            )
            return {
                "text": res.text,
                "language": res.language,
                "language_probability": res.language_probability,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "text": "",
                "language": "ko",
                "language_probability": 0.0,
                "error": str(exc),
            }

    try:
        samples, recommendations = analyze_folder(
            root,
            jsonl_path=CONFIG.voice_manifest_jsonl,
            csv_path=CONFIG.voice_manifest_csv,
            transcribe_fn=_transcribe if req.with_transcript else None,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "count": len(samples),
        "manifest_jsonl": str(CONFIG.voice_manifest_jsonl),
        "manifest_csv": str(CONFIG.voice_manifest_csv),
        "items": [asdict(s) for s in samples],
        "recommendations": [asdict(s) for s in recommendations],
    }


@app.get("/v1/voice/references")
def voice_references() -> Any:
    samples = load_manifest(CONFIG.voice_manifest_jsonl)
    picks = recommend_reference_samples(samples, top_k=5)
    return {"items": [asdict(s) for s in picks]}


class VoiceReferenceSetRequest(BaseModel):
    ref_audio_path: str
    ref_text: str
    voice_prompt_hash: str | None = None


@app.post("/v1/voice/reference")
def voice_reference(req: VoiceReferenceSetRequest) -> Any:
    if not Path(req.ref_audio_path).is_file():
        raise HTTPException(status_code=400, detail=f"기준 음성 파일이 없습니다: {req.ref_audio_path}")
    CONFIG.voice_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "ref_audio_path": req.ref_audio_path,
        "ref_text": req.ref_text,
        "voice_prompt_hash": req.voice_prompt_hash,
        "updated_at": time.time(),
    }
    CONFIG.voice_selection_path.write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True}


class CacheClearRequest(BaseModel):
    max_age_sec: float = 7 * 24 * 3600


@app.post("/v1/voice/cache/clear")
def cache_clear(req: CacheClearRequest) -> Any:
    removed = clear_generated_audio_cache(max_age_sec=float(req.max_age_sec))
    return {"ok": True, "removed": removed}


@app.post("/shutdown")
def shutdown() -> Any:
    global _should_exit  # noqa: PLW0603
    with _shutdown_lock:
        _should_exit = True

    def _kill() -> None:
        time.sleep(0.25)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_kill, daemon=True).start()
    return {"ok": True}


def _run_uvicorn() -> None:
    import uvicorn

    uvicorn.run(
        "services.voice_runtime.app:app",
        host=CONFIG.api_host,
        port=CONFIG.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    _run_uvicorn()
