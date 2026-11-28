import json
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from iris.infrastructure.ollama_client import OllamaClient
from iris.infrastructure.openai_compat_client import stream_chat


@pytest.fixture
def provider():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.reply({"models": [{"name": "fixture", "context_length": 8192}]})

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, data))
            if self.path == "/api/show":
                return self.reply({"model_info": {"test.context_length": 16384}, "capabilities": ["tools"]})
            ollama = self.path == "/api/chat"
            error = {"error": "fixture provider failed"} if ollama else {"error": {"message": "fixture provider failed"}}
            chunks = [{"message": {"content": "fixture"}}] if ollama else [{"choices": [{"delta": {"content": "fixture"}}]}]
            if data["model"] == "failure":
                chunks.append(error)
            else:
                chunks.append({"done": True, "done_reason": "stop", "eval_count": 3} if ollama else "[DONE]")
            prefix = "" if ollama else "data: "
            payload = "".join(prefix + (json.dumps(chunk) if isinstance(chunk, dict) else chunk) + "\n\n"
                              for chunk in chunks).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def reply(self, data):
            payload = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            worker.join(timeout=3)


@pytest.mark.parametrize("kind", ["ollama", "openai"])
def test_provider_stream_reports_in_band_errors_and_can_be_closed(provider, kind):
    url, requests = provider
    ollama = OllamaClient(url)
    messages = [{"role": "user", "content": "fixture"}]

    def stream(model):
        if kind == "ollama":
            return ollama.stream_chat(model, messages)
        return stream_chat(url + "/v1", "", model, messages)

    assert ollama.openai_context_budget("fixture", requested=32000) == (16384, 8192, 16384, True)
    assert list(stream("fixture"))[-1]["done"]
    if kind == "ollama":
        assert requests[-1][1]["options"]["num_ctx"] == 16384
    with closing(stream("failure")) as chunks:
        assert next(chunks)["content"] == "fixture"
        with pytest.raises(RuntimeError, match="fixture provider failed"):
            next(chunks)
    with closing(stream("failure")) as chunks:
        assert next(chunks)["content"] == "fixture"
    assert [data["model"] for path, data in requests if path.endswith(("/chat", "/completions"))] == [
        "fixture", "failure", "failure",
    ]
