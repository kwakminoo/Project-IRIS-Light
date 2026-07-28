from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from iris.audio.voice_runtime_client import VoiceRuntimeClient


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
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            temp_path = Path(f.name)
            f.write(self._wav_bytes)
        try:
            res = client.transcribe_wav_file(
                temp_path,
                model_name=self._model_name,
                language=self._language,
                vad_filter=True,
                beam_size=5,
                condition_on_previous_text=False,
            )
            self.finished_ok.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            try:
                temp_path.unlink()
            except Exception:
                pass


class TTSSynthesisWorker(QThread):
    finished_ok = pyqtSignal(object)  # dict
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        runtime_url: str,
        text: str,
        voice_prompt_hash: str,
        model_name: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._runtime_url = runtime_url
        self._text = text
        self._voice_prompt_hash = voice_prompt_hash
        self._model_name = model_name

    def run(self) -> None:
        client = VoiceRuntimeClient(base_url=self._runtime_url)
        try:
            res = client.tts_speech(
                text=self._text,
                voice_prompt_hash=self._voice_prompt_hash,
                tts_model_name=self._model_name,
            )
            self.finished_ok.emit(res)
        except Exception as exc:  # noqa: BLE001
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
