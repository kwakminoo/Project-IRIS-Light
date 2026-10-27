from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest import TestCase

from iris.engine import ChatTranscript, EngineError, EngineErrorCode, Role
from iris.engine.types import DANGEROUS_ACTIONS, IRIS_ENGINE_TOOLS
from iris.infrastructure.hermes_client import HermesInferenceTarget


def _send_payload() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "IRIS control: use iris_invoke"},
        {
            "role": "user",
            "content": "what is in the note?",
            "model_content": "what is in the note?\n\nIRIS supplied attachment data: note.txt",
        },
        {"role": "assistant", "content": "It is a shopping list."},
        {"role": "user", "content": "write it to list.txt"},
    ]


class ChatTranscriptTests(TestCase):
    def test_parse_accepts_system_history_and_trailing_user(self) -> None:
        transcript = ChatTranscript.parse(_send_payload())
        self.assertEqual(
            [message.role for message in transcript.messages],
            [Role.SYSTEM, Role.USER, Role.ASSISTANT, Role.USER],
        )
        self.assertEqual(
            transcript.messages[1].content,
            "what is in the note?\n\nIRIS supplied attachment data: note.txt",
        )
        prior, utterance = transcript.split_for_agent()
        self.assertEqual(len(prior), 3)
        self.assertEqual(prior[-1].role, Role.ASSISTANT)
        self.assertEqual(utterance, "write it to list.txt")

    def test_parse_uses_display_content_when_model_content_is_empty(self) -> None:
        transcript = ChatTranscript.parse(
            [
                {"role": "user", "content": "shown text", "model_content": ""},
            ]
        )
        self.assertEqual(transcript.messages[0].content, "shown text")

    def test_parse_rejects_unknown_role(self) -> None:
        with self.assertRaises(EngineError) as ctx:
            ChatTranscript.parse([{"role": "tool", "content": "x"}])
        self.assertEqual(ctx.exception.code, EngineErrorCode.PROTOCOL)

    def test_parse_rejects_missing_content(self) -> None:
        with self.assertRaises(EngineError) as ctx:
            ChatTranscript.parse([{"role": "user"}])
        self.assertEqual(ctx.exception.code, EngineErrorCode.PROTOCOL)

    def test_parse_rejects_empty_list(self) -> None:
        with self.assertRaises(EngineError) as ctx:
            ChatTranscript.parse([])
        self.assertEqual(ctx.exception.code, EngineErrorCode.PROTOCOL)

    def test_parse_returns_frozen_transcript(self) -> None:
        transcript = ChatTranscript.parse(_send_payload())
        with self.assertRaises(FrozenInstanceError):
            transcript.messages = ()  # type: ignore[misc]

    def test_split_for_agent_rejects_non_user_tail(self) -> None:
        transcript = ChatTranscript.parse(
            [
                {"role": "system", "content": "IRIS control"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ]
        )
        with self.assertRaises(EngineError) as ctx:
            transcript.split_for_agent()
        self.assertEqual(ctx.exception.code, EngineErrorCode.NO_USER_UTTERANCE)
        self.assertIsInstance(ctx.exception, Exception)
        self.assertNotEqual(type(ctx.exception), Exception)


class EngineTypeExportTests(TestCase):
    def test_chat_transcript_is_public_and_tool_catalog_is_not(self) -> None:
        import iris.engine as engine

        self.assertIn("ChatTranscript", engine.__all__)
        self.assertNotIn("IRIS_ENGINE_TOOLS", engine.__all__)
        self.assertNotIn("DANGEROUS_ACTIONS", engine.__all__)

    def test_private_catalogs_match_the_grafts(self) -> None:
        self.assertEqual(
            IRIS_ENGINE_TOOLS,
            ("iris_get_state", "iris_get_catalog", "iris_invoke"),
        )
        self.assertEqual(
            DANGEROUS_ACTIONS,
            frozenset(
                {
                    "project.write_file",
                    "project.run",
                    "project.rename_file",
                    "project.create_scaffold",
                }
            ),
        )

    def test_stateless_turn_reuses_hermes_inference_target(self) -> None:
        from iris.engine import CancelToken, StatelessTurn

        turn = StatelessTurn(
            transcript=ChatTranscript.parse([{"role": "user", "content": "hi"}]),
            model=HermesInferenceTarget(model="llama3.2", provider="custom"),
            cancel=CancelToken(),
        )
        self.assertIsInstance(turn.model, HermesInferenceTarget)
        self.assertEqual(EngineErrorCode.AUTH.value, "auth")
