"""Provider stream token counts normalized for UI analytics."""

from __future__ import annotations

from dataclasses import dataclass


def _count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


@dataclass(frozen=True)
class TokenUsage:
    tokens_in: int = 0
    tokens_out: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "tokens_in", _count(self.tokens_in))
        object.__setattr__(self, "tokens_out", _count(self.tokens_out))


def parse_stream_usage(raw: object) -> TokenUsage | None:
    """Parse OpenAI-style usage or an Ollama terminal chunk; never raise."""
    if not isinstance(raw, dict):
        return None
    usage = raw.get("usage")
    if isinstance(usage, dict):
        return TokenUsage(
            usage.get("prompt_tokens", usage.get("input_tokens", 0)),
            usage.get("completion_tokens", usage.get("output_tokens", 0)),
        )
    if "prompt_eval_count" in raw or "eval_count" in raw:
        return TokenUsage(raw.get("prompt_eval_count", 0), raw.get("eval_count", 0))
    return None
