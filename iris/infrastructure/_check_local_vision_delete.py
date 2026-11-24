"""local_vision.delete_model contract (no live Ollama unless IRIS_LIVE_OLLAMA=1)."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from unittest import mock

from iris.infrastructure.local_vision import delete_model, forget_cache, pull_model


def _src() -> str:
    return Path(inspect.getfile(delete_model)).read_text(encoding="utf-8")


def main() -> None:
    src = _src()
    assert "/api/delete" in src
    assert "forget_cache" in inspect.getsource(delete_model)

    # Mirror pull_model: Optional[str] — None ok, str on failure/cancel
    assert delete_model.__annotations__.get("return") == pull_model.__annotations__.get("return")

    err = delete_model("http://127.0.0.1:9", "nope:tag", should_abort=lambda: True)
    assert isinstance(err, str) and err, err

    # Failure path without live Ollama: stub urlopen → short error string
    with mock.patch(
        "iris.infrastructure.local_vision.urlopen",
        side_effect=OSError("refused"),
    ):
        bad = delete_model("http://127.0.0.1:11434", "unit-test-missing:tag")
    assert bad == "refused"

    # Request must be DELETE with JSON body key "model" (Ollama docs + pull_model)
    captured: list = []

    class _Resp:
        def read(self) -> bytes:
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _capture(req, timeout=None):
        captured.append(req)
        return _Resp()

    from iris.infrastructure import local_vision as lv

    lv._cache["k"] = (0.0, "m", "ok")
    with mock.patch("iris.infrastructure.local_vision.urlopen", side_effect=_capture):
        assert delete_model("http://127.0.0.1:11434", "stub:tag") is None
    assert len(captured) == 1, captured
    req = captured[0]
    assert req.get_method() == "DELETE", req.get_method()
    payload = json.loads(req.data.decode("utf-8"))
    assert payload == {"model": "stub:tag"}, payload
    assert lv._cache == {}

    if os.environ.get("IRIS_LIVE_OLLAMA") == "1":
        live = delete_model(
            os.environ.get("IRIS_OLLAMA_URL") or "http://127.0.0.1:11434",
            "iris-unit-delete-missing-zzzz:tag",
        )
        assert live is None or isinstance(live, str), live

    forget_cache()
    print("local_vision delete_model self-check ok")


if __name__ == "__main__":
    main()
