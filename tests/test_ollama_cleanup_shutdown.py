import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from iris.ui.workers.ollama_workers import OllamaModelsVerifyWorker


class OllamaCleanupShutdownTests(unittest.TestCase):
    def test_interruption_exits_while_provider_probe_is_in_flight(self):
        started = threading.Event()
        release = threading.Event()

        class Client:
            def __init__(self, _base_url):
                pass

            def list_chat_models(self, *, probe_cloud):
                return [SimpleNamespace(name="test-model")]

            def classify_model(self, _name):
                started.set()
                release.wait(timeout=3)
                return "available", "yes"

        worker = OllamaModelsVerifyWorker("http://127.0.0.1:1/v1")
        with patch("iris.ui.workers.ollama_workers.OllamaClient", Client):
            worker.start()
            try:
                self.assertTrue(started.wait(1), "model verification did not start")
                worker.requestInterruption()
                self.assertTrue(worker.wait(700), "window close waits on the provider probe")
            finally:
                release.set()
                worker.wait(3500)
