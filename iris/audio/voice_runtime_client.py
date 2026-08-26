from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class VoiceRuntimeHealth:
    status: str
    pid: int
    mock_mode: bool


class VoiceRuntimeError(RuntimeError):
    pass


class VoiceRuntimeClient:
    def __init__(self, *, base_url: str = "http://127.0.0.1:18765", timeout_sec: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout_sec)

    def set_base_url(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def _post_json(self, path: str, payload: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self._timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise VoiceRuntimeError(f"Voice runtime HTTP {e.code}: {raw[:400]}") from e
        except Exception as e:
            raise VoiceRuntimeError(f"Voice runtime request failed: {e}") from e

    def _get_json(self, path: str, *, timeout: float | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self._timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise VoiceRuntimeError(f"Voice runtime HTTP {e.code}: {raw[:400]}") from e
        except Exception as e:
            raise VoiceRuntimeError(f"Voice runtime request failed: {e}") from e

    def health(self, *, timeout: float | None = None) -> VoiceRuntimeHealth:
        res = self._get_json("/health", timeout=timeout)
        return VoiceRuntimeHealth(
            status=str(res.get("status") or "unknown"),
            pid=int(res.get("pid") or 0),
            mock_mode=bool(res.get("mock_mode") or False),
        )

    def shutdown(self) -> None:
        _ = self._post_json("/shutdown", {"ok": True}, timeout=5.0)

    def transcribe_wav_file(
        self,
        wav_path: Path,
        *,
        model_name: str = "small",
        language: str = "ko",
        vad_filter: bool = True,
        beam_size: int = 5,
        condition_on_previous_text: bool = False,
        compute_type: str | None = None,
    ) -> dict[str, Any]:
        return self.transcribe_wav_bytes(
            wav_path.read_bytes(),
            model_name=model_name,
            language=language,
            vad_filter=vad_filter,
            beam_size=beam_size,
            condition_on_previous_text=condition_on_previous_text,
            compute_type=compute_type,
        )

    def transcribe_wav_bytes(
        self,
        wav_bytes: bytes,
        *,
        model_name: str = "small",
        language: str = "ko",
        vad_filter: bool = True,
        beam_size: int = 5,
        condition_on_previous_text: bool = False,
        compute_type: str | None = None,
    ) -> dict[str, Any]:
        del compute_type
        started = time.perf_counter()
        qs = urllib.parse.urlencode(
            {
                "model_name": model_name,
                "language": language,
                "vad_filter": "true" if vad_filter else "false",
                "beam_size": int(beam_size),
                "condition_on_previous_text": "true" if condition_on_previous_text else "false",
            }
        )
        url = f"{self._base_url}/v1/audio/transcriptions/raw?{qs}"
        req = urllib.request.Request(
            url,
            data=wav_bytes,
            method="POST",
            headers={
                "Content-Type": "audio/wav",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                upload_done = time.perf_counter()
                body = resp.read().decode("utf-8", errors="replace")
                payload = json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise VoiceRuntimeError(f"Voice runtime HTTP {e.code}: {raw[:400]}") from e
        except Exception as e:
            raise VoiceRuntimeError(f"Voice runtime request failed: {e}") from e
        finished = time.perf_counter()
        if isinstance(payload, dict):
            payload["upload_sec"] = max(0.0, upload_done - started)
            payload["transcribe_sec"] = max(0.0, finished - upload_done)
        return payload if isinstance(payload, dict) else {}

    def stt_warmup(self, *, model_name: str = "small", wait: bool = False) -> dict[str, Any]:
        return self._post_json(
            "/v1/audio/stt/warmup",
            {"model_name": model_name, "wait": bool(wait)},
            timeout=max(self._timeout, 600.0) if wait else self._timeout,
        )

    def voice_prepare(
        self,
        *,
        ref_audio_path: str,
        ref_text: str,
        tts_model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        voice_prompt_hash: str | None = None,
    ) -> str:
        if not Path(ref_audio_path).is_file():
            raise VoiceRuntimeError(f"기준 음성 파일이 없습니다: {ref_audio_path}")
        payload = {
            "ref_audio_path": ref_audio_path,
            "ref_text": ref_text,
            "tts_model_name": tts_model_name,
            "voice_prompt_hash": voice_prompt_hash,
        }
        res = self._post_json("/v1/voice/prepare", payload)
        return str(res.get("voice_prompt_hash") or "")

    def voice_set_reference(
        self,
        *,
        ref_audio_path: str,
        ref_text: str,
        voice_prompt_hash: str | None = None,
    ) -> None:
        if not Path(ref_audio_path).is_file():
            raise VoiceRuntimeError(f"기준 음성 파일이 없습니다: {ref_audio_path}")
        payload = {
            "ref_audio_path": ref_audio_path,
            "ref_text": ref_text,
            "voice_prompt_hash": voice_prompt_hash,
        }
        _ = self._post_json("/v1/voice/reference", payload)

    def voice_analyze(
        self,
        root: str,
        *,
        with_transcript: bool = True,
        stt_model_name: str = "small",
        language: str = "ko",
    ) -> dict[str, Any]:
        payload = {
            "root": root,
            "with_transcript": bool(with_transcript),
            "stt_model_name": stt_model_name,
            "language": language,
        }
        return self._post_json("/v1/voice/analyze", payload, timeout=max(self._timeout, 600.0))

    def voice_references(self) -> list[dict[str, Any]]:
        res = self._get_json("/v1/voice/references")
        items = res.get("items") or []
        return items if isinstance(items, list) else []

    def clear_cache(self, *, max_age_sec: float = 7 * 24 * 3600) -> int:
        res = self._post_json("/v1/voice/cache/clear", {"max_age_sec": float(max_age_sec)})
        return int(res.get("removed") or 0)

    def voice_profile(self) -> dict[str, Any]:
        """커밋된 보이스 프로필 정보. available=False면 수동 기준 음성이 필요하다."""
        try:
            return self._get_json("/v1/voice/profile")
        except VoiceRuntimeError:
            return {"available": False, "tones": {}}

    def tts_speech(
        self,
        *,
        text: str,
        voice_prompt_hash: str = "",
        tts_model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        tone: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "text": text,
            "voice_prompt_hash": voice_prompt_hash,
            "tts_model_name": tts_model_name,
            "tone": tone,
        }
        # 이 노트북 기준 한 문장 생성에 1분 이상 걸린다(RTF 10배 안팎).
        # 기본 60초 타임아웃으로는 정상 생성도 실패로 잡힌다.
        return self._post_json("/v1/audio/speech", payload, timeout=max(self._timeout, 600.0))

    def warmup(
        self,
        *,
        tts_model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        wait: bool = False,
    ) -> dict[str, Any]:
        return self._post_json(
            "/v1/audio/warmup",
            {"tts_model_name": tts_model_name, "wait": bool(wait)},
            timeout=max(self._timeout, 600.0) if wait else self._timeout,
        )

    def iter_tts_speech_stream(
        self,
        *,
        text: str,
        voice_prompt_hash: str = "",
        tts_model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        tone: str | None = None,
        engine: str = "qwen",
        custom_speaker: str = "iris",
        custom_model_path: str = "",
        gpt_sovits_url: str = "http://127.0.0.1:9880",
        voice_data_dir: str = "",
        tone_routing: bool = True,
        cancel_event: Any | None = None,
        response_callback: Callable[[Any | None], None] | None = None,
    ):
        payload = {
            "text": text,
            "voice_prompt_hash": voice_prompt_hash,
            "tts_model_name": tts_model_name,
            "tone": tone,
            "engine": engine,
            "custom_speaker": custom_speaker,
            "custom_model_path": custom_model_path,
            "gpt_sovits_url": gpt_sovits_url,
            "voice_data_dir": voice_data_dir,
            "tone_routing": bool(tone_routing),
        }
        url = f"{self._base_url}/v1/audio/speech/stream"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/x-ndjson",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=max(self._timeout, 600.0)) as resp:
                if response_callback is not None:
                    response_callback(resp)
                if cancel_event is not None and cancel_event.is_set():
                    return
                try:
                    for raw in resp:
                        if cancel_event is not None and cancel_event.is_set():
                            return
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise VoiceRuntimeError(f"TTS stream JSON 오류: {line[:120]}") from exc
                        if not isinstance(event, dict):
                            continue
                        if event.get("type") == "error":
                            raise VoiceRuntimeError(str(event.get("message") or "TTS stream error"))
                        yield event
                finally:
                    if response_callback is not None:
                        response_callback(None)
        except VoiceRuntimeError:
            raise
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise VoiceRuntimeError(f"Voice runtime HTTP {e.code}: {raw[:400]}") from e
        except Exception as e:
            raise VoiceRuntimeError(f"Voice runtime stream failed: {e}") from e
