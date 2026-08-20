from __future__ import annotations

from threading import Event, Lock

from PyQt6.QtCore import QThread, pyqtSignal

from iris.audio.voice_runtime_client import VoiceRuntimeClient
from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager


class STTTranscriptionWorker(QThread):
    finished_ok = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(
        self,
        wav_bytes: bytes,
        *,
        runtime_url: str,
        model_name: str = "small",
        language: str = "ko",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._wav_bytes = wav_bytes
        self._runtime_url = runtime_url
        self._model_name = model_name
        self._language = language

    def run(self) -> None:
        client = VoiceRuntimeClient(base_url=self._runtime_url)
        try:
            res = client.transcribe_wav_bytes(
                self._wav_bytes,
                model_name=self._model_name,
                language=self._language,
                vad_filter=True,
                beam_size=5,
                condition_on_previous_text=False,
            )
            self.finished_ok.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class STTWarmupWorker(QThread):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, *, runtime_url: str, model_name: str, parent=None) -> None:
        super().__init__(parent)
        self._runtime_url = runtime_url
        self._model_name = model_name

    def run(self) -> None:
        client = VoiceRuntimeClient(base_url=self._runtime_url)
        try:
            self.finished_ok.emit(client.stt_warmup(model_name=self._model_name, wait=False))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TTSSynthesisWorker(QThread):
    finished_ok = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        runtime_url: str,
        text: str,
        voice_prompt_hash: str = "",
        model_name: str,
        tone: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._runtime_url = runtime_url
        self._text = text
        self._voice_prompt_hash = voice_prompt_hash
        self._model_name = model_name
        self._tone = tone

    def run(self) -> None:
        client = VoiceRuntimeClient(base_url=self._runtime_url)
        try:
            res = client.tts_speech(
                text=self._text,
                voice_prompt_hash=self._voice_prompt_hash,
                tts_model_name=self._model_name,
                tone=self._tone,
            )
            self.finished_ok.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TTSStreamWorker(QThread):
    started_fmt = pyqtSignal(int)
    chunk = pyqtSignal(bytes)
    prepared = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        runtime_url: str,
        text: str,
        payload: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._runtime_url = runtime_url
        self._text = text
        self._payload = dict(payload or {})
        # Reference-prompt preparation is network/model work, so keep it off
        # the UI thread when a non-profile Qwen voice has not been prepared yet.
        self._prepare_ref_audio = str(self._payload.pop("_prepare_ref_audio", "") or "")
        self._prepare_ref_text = str(self._payload.pop("_prepare_ref_text", "") or "")
        self._cancel = Event()
        self._response_lock = Lock()
        self._stream_response = None

    def request_cancel(self) -> None:
        self._cancel.set()
        self.requestInterruption()
        with self._response_lock:
            response = self._stream_response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def _is_cancelled(self) -> bool:
        return self._cancel.is_set() or self.isInterruptionRequested()

    def _set_stream_response(self, response) -> None:
        with self._response_lock:
            self._stream_response = response
        # request_cancel can win just before urlopen hands us the response.
        # Close it here as well so the worker never waits for the next NDJSON line.
        if response is not None and self._is_cancelled():
            try:
                response.close()
            except Exception:
                pass

    def run(self) -> None:
        import base64

        client = VoiceRuntimeClient(base_url=self._runtime_url)
        try:
            if self._prepare_ref_audio and not self._payload.get("voice_prompt_hash"):
                voice_hash = client.voice_prepare(
                    ref_audio_path=self._prepare_ref_audio,
                    ref_text=self._prepare_ref_text,
                    tts_model_name=str(self._payload.get("tts_model_name") or "Qwen/Qwen3-TTS-12Hz-0.6B-Base"),
                    voice_prompt_hash=None,
                )
                if self._is_cancelled():
                    return
                self._payload["voice_prompt_hash"] = voice_hash
                self.prepared.emit(voice_hash)
            stream = client.iter_tts_speech_stream(
                text=self._text,
                cancel_event=self._cancel,
                response_callback=self._set_stream_response,
                **self._payload,
            )
            try:
                for event in stream:
                    if self._is_cancelled():
                        return
                    kind = str(event.get("type") or "")
                    if kind == "start":
                        self.started_fmt.emit(int(event.get("sample_rate") or 24000))
                    elif kind == "chunk":
                        raw = str(event.get("pcm_b64") or "")
                        if raw and not self._is_cancelled():
                            self.chunk.emit(base64.b64decode(raw))
            finally:
                if self._is_cancelled():
                    close = getattr(stream, "close", None)
                    if callable(close):
                        close()
            if not self._is_cancelled():
                self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            if not self._is_cancelled():
                self.failed.emit(str(exc))


class TTSWarmupWorker(QThread):
    finished_ok = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(self, *, runtime_url: str, model_name: str, parent=None) -> None:
        super().__init__(parent)
        self._runtime_url = runtime_url
        self._model_name = model_name

    def run(self) -> None:
        client = VoiceRuntimeClient(base_url=self._runtime_url)
        try:
            self.finished_ok.emit(client.warmup(tts_model_name=self._model_name, wait=False))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class TTSRuntimeBootstrapWorker(QThread):
    """Start the local voice runtime and schedule CUDA warmup away from the UI thread."""

    finished_ok = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        runtime: VoiceRuntimeProcessManager,
        runtime_url: str,
        model_name: str,
        mock_mode: bool,
        warmup: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._runtime = runtime
        self._runtime_url = runtime_url
        self._model_name = model_name
        self._mock_mode = mock_mode
        self._warmup = warmup
        self._cancel = Event()

    def request_cancel(self) -> None:
        self._cancel.set()
        self.requestInterruption()

    def run(self) -> None:
        try:
            status = self._runtime.ensure_started(
                mock_mode=self._mock_mode,
                cancel_event=self._cancel,
            )
            if self._cancel.is_set():
                return
            payload: dict[str, object] = {"running": bool(status.running)}
            if status.running and self._warmup and not self._mock_mode:
                payload.update(
                    VoiceRuntimeClient(base_url=self._runtime_url).warmup(
                        tts_model_name=self._model_name,
                        wait=False,
                    )
                )
            if not self._cancel.is_set():
                self.finished_ok.emit(payload)
        except Exception as exc:  # noqa: BLE001
            if not self._cancel.is_set():
                self.failed.emit(str(exc))


class VoiceAnalyzeWorker(QThread):
    finished_ok = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        runtime_url: str,
        root: str,
        with_transcript: bool = True,
        stt_model_name: str = "small",
        language: str = "ko",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._runtime_url = runtime_url
        self._root = root
        self._with_transcript = with_transcript
        self._stt_model_name = stt_model_name
        self._language = language

    def run(self) -> None:
        client = VoiceRuntimeClient(base_url=self._runtime_url, timeout_sec=600.0)
        try:
            res = client.voice_analyze(
                self._root,
                with_transcript=self._with_transcript,
                stt_model_name=self._stt_model_name,
                language=self._language,
            )
            self.finished_ok.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
