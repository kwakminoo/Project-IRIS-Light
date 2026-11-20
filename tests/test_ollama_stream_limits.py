import json
import unittest
from unittest.mock import patch

from iris.infrastructure import ollama_client


class _Response:
    def __init__(self, *, body=b"{}", lines=()):
        self.body = body
        self.lines = tuple(lines)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body

    def __iter__(self):
        return iter(self.lines)


class OllamaStreamLimitTests(unittest.TestCase):
    def test_chat_uses_model_context_with_cap_and_unlimited_prediction(self):
        requests = []

        def open_url(request, **_kwargs):
            requests.append(request)
            if request.full_url.endswith("/api/show"):
                return _Response(
                    body=json.dumps(
                        {"model_info": {"test.context_length": 131072}}
                    ).encode()
                )
            return _Response(
                lines=(
                    b'{"message":{"content":"complete"},"done":false}\n',
                    b'{"message":{"content":""},"done":true,"done_reason":"stop"}\n',
                )
            )

        with patch.object(ollama_client, "urlopen", side_effect=open_url):
            events = list(
                ollama_client.OllamaClient("http://127.0.0.1:11434/v1").stream_chat(
                    "test", [{"role": "user", "content": "long answer"}]
                )
            )

        payload = json.loads(requests[-1].data)
        self.assertEqual(
            payload["options"],
            {"num_ctx": ollama_client.OLLAMA_CHAT_CONTEXT_CAP, "num_predict": -1},
        )
        self.assertEqual(events[-1]["done_reason"], "stop")


if __name__ == "__main__":
    unittest.main()
