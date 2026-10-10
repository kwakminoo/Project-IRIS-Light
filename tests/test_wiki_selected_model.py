"""위키 모델 호출은 채팅에서 고른 제공자로 간다."""

from types import SimpleNamespace
from unittest.mock import patch

from iris.knowledge.wiki_filing import open_classifier
from iris.knowledge.wiki_summarize import summarize_for_wiki
from iris.runtime.backend_route import ask_selected_model
from iris.storage.api_providers import ApiProvider, upsert_api_provider


class _MemDb:
    def __init__(self) -> None:
        self.prefs: dict[str, str] = {}

    def get_preference(self, key: str, default: str = "") -> str:
        return self.prefs.get(key, default)

    def set_preference(self, key: str, value: str) -> None:
        self.prefs[key] = value


def _nvidia_db():
    db = _MemDb()
    upsert_api_provider(
        db,
        ApiProvider(
            id="nid",
            name="NVIDIA NIM",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key="secret",
            models=["nvidia/nemotron-3-nano"],
        ),
    )
    return db


def _settings():
    return SimpleNamespace(hermes_enabled=False, ollama_base_url="http://127.0.0.1:11434/v1")


def test_api_runtime_id_goes_to_that_provider():
    db = _nvidia_db()
    with patch("iris.ui.workers.backend_call.collect_reply", return_value="요약문") as collect:
        text = ask_selected_model(
            _settings(),
            db,
            "api:nid:nvidia/nemotron-3-nano",
            "요약해",
            system="sys",
        )
    assert text == "요약문"
    route = collect.call_args.args[0]
    assert route.backend == "api"
    assert route.model == "nvidia/nemotron-3-nano"
    assert route.base_url == "https://integrate.api.nvidia.com/v1"
    assert collect.call_args.args[1][0]["role"] == "system"


def test_ollama_name_stays_on_ollama():
    with patch("iris.ui.workers.backend_call.collect_reply", return_value="ok") as collect:
        ask_selected_model(_settings(), None, "qwen3:8b", "hi")
    route = collect.call_args.args[0]
    assert route.backend == "ollama"
    assert route.model == "qwen3:8b"


def test_missing_provider_does_not_call_ollama():
    with patch("iris.ui.workers.backend_call.collect_reply") as collect:
        try:
            ask_selected_model(_settings(), _nvidia_db(), "api:missing:foo", "hi")
        except RuntimeError as exc:
            assert "제공자" in str(exc)
        else:
            raise AssertionError("missing provider should fail")
    collect.assert_not_called()


def test_wiki_summary_keeps_runtime_id():
    settings = _settings()
    db = _nvidia_db()
    with patch(
        "iris.runtime.backend_route.ask_selected_model", return_value="요약",
    ) as ask:
        text = summarize_for_wiki(
            "자료구조란 자료를 효율적으로 저장하는 방법이다.",
            model="api:nid:nvidia/nemotron-3-nano",
            ollama_base_url="http://127.0.0.1:11434/v1",
            settings=settings,
            db=db,
        )
    assert text == "요약"
    assert ask.call_args.args[2] == "api:nid:nvidia/nemotron-3-nano"
    assert ask.call_args.args[0] is settings
    assert ask.call_args.args[1] is db


def test_classifier_uses_selected_model():
    settings = _settings()
    db = _nvidia_db()
    with patch(
        "iris.runtime.backend_route.ask_selected_model", return_value='{"place":"study"}',
    ) as ask:
        _embedder, namer = open_classifier(
            "http://127.0.0.1:11434/v1",
            None,
            "api:nid:nvidia/nemotron-3-nano",
            db=db,
            settings=settings,
        )
        assert namer is not None
        namer("분류해")
    assert ask.call_args.args[2] == "api:nid:nvidia/nemotron-3-nano"


if __name__ == "__main__":
    test_api_runtime_id_goes_to_that_provider()
    test_ollama_name_stays_on_ollama()
    test_missing_provider_does_not_call_ollama()
    test_wiki_summary_keeps_runtime_id()
    test_classifier_uses_selected_model()
    print("wiki selected model ok")
