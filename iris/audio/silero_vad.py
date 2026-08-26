"""ONNX Silero VAD. 메인 venv에 torch를 넣지 않는다."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

import numpy as np

LOGGER = logging.getLogger(__name__)

_WINDOW = 512  # 16 kHz, silero v5
_SR = 16000
_MODEL_URLS = (
    "https://github.com/snakers4/silero-vad/raw/v5.1.2/src/silero_vad/data/silero_vad.onnx",
    "https://cdn.jsdelivr.net/gh/snakers4/silero-vad@v5.1.2/src/silero_vad/data/silero_vad.onnx",
)
_ORT_LOCK = threading.Lock()
_ORT_INSTALL_TRIED = False


def _cache_path() -> Path:
    return Path.home() / ".iris-light" / "models" / "silero_vad.onnx"


def ensure_onnxruntime() -> bool:
    """없으면 현재 interpreter에 onnxruntime을 설치한다. 실패해도 RMS-only로 진행."""
    global _ORT_INSTALL_TRIED
    try:
        import onnxruntime  # noqa: F401

        return True
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        return False
    if os.environ.get("IRIS_SKIP_ORT_INSTALL") == "1":
        return False
    with _ORT_LOCK:
        try:
            import onnxruntime  # noqa: F401

            return True
        except Exception:
            pass
        if _ORT_INSTALL_TRIED:
            return False
        _ORT_INSTALL_TRIED = True
        LOGGER.info("onnxruntime 없음 — pip install 시도")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "onnxruntime>=1.17.0"],
                check=True,
                timeout=180,
                capture_output=True,
                text=True,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("onnxruntime 설치 실패: %s", exc)
            return False
        try:
            import onnxruntime  # noqa: F401

            return True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("onnxruntime import 실패: %s", exc)
            return False


class SileroVad:
    """16 kHz int16 청크를 받아 speech probability (0..1)를 반환."""

    def __init__(
        self,
        *,
        score_fn: Callable[[np.ndarray], float] | None = None,
        load_async: bool = True,
    ) -> None:
        self._score_fn = score_fn
        self._session = None
        self._state: np.ndarray | None = None
        self._context: np.ndarray | None = None
        self._pending = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self._available = score_fn is not None
        if score_fn is None:
            if load_async:
                threading.Thread(target=self._try_load, name="iris-silero-vad", daemon=True).start()
            else:
                self._try_load()

    @property
    def available(self) -> bool:
        return self._available

    def reset(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)
        with self._lock:
            if self._session is not None:
                self._state = np.zeros((2, 1, 128), dtype=np.float32)
                self._context = np.zeros((1, 64), dtype=np.float32)

    def speech_prob(self, pcm_int16: bytes) -> float:
        if not self._available and self._score_fn is None:
            return 0.0
        if not pcm_int16:
            return 0.0
        usable = len(pcm_int16) - (len(pcm_int16) % 2)
        samples = np.frombuffer(pcm_int16[:usable], dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return 0.0
        self._pending = np.concatenate([self._pending, samples])
        probs: list[float] = []
        while self._pending.size >= _WINDOW:
            window = self._pending[:_WINDOW]
            self._pending = self._pending[_WINDOW:]
            probs.append(self._score(window))
        if not probs:
            return 0.0
        return float(max(probs))

    def _score(self, window: np.ndarray) -> float:
        if self._score_fn is not None:
            return float(max(0.0, min(1.0, self._score_fn(window))))
        with self._lock:
            session = self._session
            if session is None:
                return 0.0
            try:
                inputs = session.get_inputs()
                names = {i.name for i in inputs}
                feed: dict[str, object] = {}
                audio = window.reshape(1, -1).astype(np.float32)
                if "input" in names:
                    feed["input"] = audio
                if "context" in names:
                    if self._context is None:
                        self._context = np.zeros((1, 64), dtype=np.float32)
                    feed["context"] = self._context
                if "state" in names:
                    if self._state is None:
                        self._state = np.zeros((2, 1, 128), dtype=np.float32)
                    feed["state"] = self._state
                if "sr" in names:
                    feed["sr"] = np.array(_SR, dtype=np.int64)
                out = session.run(None, feed)
                prob = float(np.squeeze(out[0]))
                if len(out) > 1:
                    nxt = out[1]
                    if getattr(nxt, "shape", None) == (2, 1, 128):
                        self._state = nxt
                    elif len(getattr(nxt, "shape", ())) >= 1 and nxt.shape[-1] == 64:
                        self._context = nxt
                if len(out) > 2 and getattr(out[2], "shape", None) == (2, 1, 128):
                    self._state = out[2]
                return max(0.0, min(1.0, prob))
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Silero VAD score failed: %s", exc)
                return 0.0

    def _try_load(self) -> None:
        if not ensure_onnxruntime():
            LOGGER.info("onnxruntime 없음 — Silero VAD 없이 RMS gate만 사용")
            return
        import onnxruntime as ort  # type: ignore

        path = _cache_path()
        try:
            if not path.is_file() or path.stat().st_size < 10_000:
                self._download(path)
            sess_opts = ort.SessionOptions()
            sess_opts.inter_op_num_threads = 1
            sess_opts.intra_op_num_threads = 1
            session = ort.InferenceSession(
                str(path), sess_options=sess_opts, providers=["CPUExecutionProvider"]
            )
            with self._lock:
                self._session = session
                self._state = np.zeros((2, 1, 128), dtype=np.float32)
                self._context = np.zeros((1, 64), dtype=np.float32)
                self._available = True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Silero VAD 로드 실패, RMS-only로 진행: %s", exc)

    def _download(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None
        for url in _MODEL_URLS:
            tmp = path.with_suffix(".onnx.tmp")
            try:
                req = Request(url, headers={"User-Agent": "iris-light-silero-vad"})
                with urlopen(req, timeout=30) as resp:  # noqa: S310
                    tmp.write_bytes(resp.read())
                if tmp.stat().st_size < 10_000:
                    tmp.unlink(missing_ok=True)
                    raise RuntimeError(f"Silero 모델이 너무 작음: {url}")
                tmp.replace(path)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                tmp.unlink(missing_ok=True)
                continue
        raise RuntimeError(f"Silero VAD 다운로드 실패: {last_exc}")
