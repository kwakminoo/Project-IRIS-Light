import json
import unittest
from unittest.mock import patch

from iris.infrastructure import openai_compat_client as client


class _Response:
    def __init__(self, lines=(), body=b"{}"):
        self._lines = iter(lines)
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body

    def readline(self):
        return next(self._lines, b"")


class OpenAICompatHeaderTests(unittest.TestCase):
    def test_json_and_stream_requests_set_iris_user_agent(self):
        seen = []

        def open_url(request, **_kwargs):
            seen.append(request)
            if request.full_url.endswith("/models"):
                return _Response(body=b'{"data": []}')
            return _Response(lines=(b"data: [DONE]\n",))

        with patch.object(client, "urlopen", side_effect=open_url):
            client.list_models("https://example.test/v1", "secret")
            list(
                client.stream_chat(
                    "https://example.test/v1",
                    "secret",
                    "model",
                    [{"role": "user", "content": "hi"}],
                )
            )

        self.assertEqual(len(seen), 2)
        for request in seen:
            self.assertEqual(
                request.get_header("User-agent"), client.IRIS_HTTP_USER_AGENT
            )

    def test_cloudflare_1010_does_not_retry_x_api_key(self):
        calls = []

        def attempt(_candidate, style):
            calls.append(style)
            raise client.HttpFail(403, "Cloudflare Error 1010")

        _root, _style, _data, errors = client._try_candidates(
            ["https://api.groq.com/openai/v1"], "secret", attempt
        )
        self.assertEqual(calls, ["bearer"])
        self.assertIn("HTTP 클라이언트 식별자", errors[0])


if __name__ == "__main__":
    unittest.main()
