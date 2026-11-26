from unittest import TestCase
from unittest.mock import patch

from iris.infrastructure.iris_agent_client import IrisAgentInferenceTarget
from iris.ui.workers.backend_call import BackendRoute, collect_reply


class BackgroundAgentRouteTests(TestCase):
    def test_agent_background_route_only_contacts_the_resolved_provider(self):
        messages = [{"role": "user", "content": "hello"}]
        target = IrisAgentInferenceTarget("local", "custom", "http://localhost:11434/v1")
        with (
            patch("iris.infrastructure.iris_agent_client.IrisAgentClient", side_effect=AssertionError("Gateway was reached")),
            patch("iris.infrastructure.openai_compat_client.stream_chat", return_value=iter([{"content": "ok", "done": True}])) as stream,
        ):
            self.assertEqual(collect_reply(BackendRoute("agent", "local", target=target), messages, timeout_sec=17), "ok")
            self.assertEqual(stream.call_args.args[0], target.base_url)
            self.assertEqual(stream.call_args.kwargs["timeout"], 17)
            with self.assertRaisesRegex(RuntimeError, "provider"):
                collect_reply(BackendRoute("agent", "local"), messages)
