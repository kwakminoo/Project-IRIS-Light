"""FFC-05 agent execution recovery diagnosis (not a second registry / loop).

Organizing structure: one RecoveryClass table + classifier. failure_class
(diagnosis) is recorded separately from task_outcome. Policy helpers stay pure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class RecoveryClass(str, Enum):
    SCHEMA = "schema"
    RANKING = "ranking"
    ARG_NORMALIZE = "arg_normalize"
    CONTEXT_OVERFLOW = "context_overflow"
    CONTINUATION = "continuation"
    CLEAN_EOF = "clean_eof"
    MODEL_OUTPUT_LIMIT = "model_output_limit"
    RESULT_GROUNDING = "result_grounding"
    UNCERTAIN_SIDE_EFFECT = "uncertain_side_effect"


class TaskOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"
    REFUSED = "refused"


# EngineErrorCode.value → RecoveryClass (scraped contract; keep in sync with types.py).
_ENGINE_CODE_TO_CLASS: dict[str, RecoveryClass] = {
    "truncated": RecoveryClass.MODEL_OUTPUT_LIMIT,
    "context_overflow": RecoveryClass.CONTEXT_OVERFLOW,
}

_MARKER_TO_CLASS: tuple[tuple[str, RecoveryClass], ...] = (
    ("_clean_eof", RecoveryClass.CLEAN_EOF),
    ("clean_eof", RecoveryClass.CLEAN_EOF),
    ("stream closed cleanly", RecoveryClass.CLEAN_EOF),
    ("finish_reason='length'", RecoveryClass.MODEL_OUTPUT_LIMIT),
    ("max output tokens", RecoveryClass.MODEL_OUTPUT_LIMIT),
    ("length_continue", RecoveryClass.CONTINUATION),
    ("continuation", RecoveryClass.CONTINUATION),
    ("schema_fingerprint", RecoveryClass.SCHEMA),
    ("invalid_arguments", RecoveryClass.SCHEMA),
    ("inputschema", RecoveryClass.SCHEMA),
    ("ranking", RecoveryClass.RANKING),
    ("begin tool output", RecoveryClass.RESULT_GROUNDING),
    ("begin attachment text", RecoveryClass.RESULT_GROUNDING),
    ("[자료 본문]", RecoveryClass.RESULT_GROUNDING),
    ("execution_uncertain", RecoveryClass.UNCERTAIN_SIDE_EFFECT),
)


@dataclass(frozen=True)
class RecoveryRecord:
    """Independent fields: diagnosis vs task_outcome (never collapse them)."""

    diagnosis: RecoveryClass | None
    task_outcome: TaskOutcome
    surface: str = ""
    grounded: bool | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "diagnosis": None if self.diagnosis is None else self.diagnosis.value,
            "task_outcome": self.task_outcome.value,
            "surface": self.surface,
            "grounded": self.grounded,
            "detail": self.detail,
        }


def diagnose_recovery(
    *,
    engine_code: str | None = None,
    detail: str = "",
    markers: Mapping[str, Any] | None = None,
    execution_uncertain: bool = False,
) -> RecoveryClass | None:
    """Classify failure_class from known maps/markers. Does not set task_outcome."""
    if execution_uncertain or (markers or {}).get("execution_uncertain") is True:
        return RecoveryClass.UNCERTAIN_SIDE_EFFECT
    code = str(engine_code or "").strip().lower()
    if code in _ENGINE_CODE_TO_CLASS:
        mapped = _ENGINE_CODE_TO_CLASS[code]
        # clean_eof can share truncated fail codes in upstream stubs.
        blob = f"{detail}\n{json.dumps(markers or {}, ensure_ascii=True, default=str)}".lower()
        if mapped is RecoveryClass.MODEL_OUTPUT_LIMIT and (
            "_clean_eof" in blob or "clean_eof" in blob or "stream closed cleanly" in blob
        ):
            return RecoveryClass.CLEAN_EOF
        return mapped
    blob = f"{detail}\n{json.dumps(markers or {}, ensure_ascii=True, default=str)}".lower()
    for needle, klass in _MARKER_TO_CLASS:
        if needle in blob:
            return klass
    return None


def build_recovery_record(
    *,
    task_outcome: TaskOutcome,
    engine_code: str | None = None,
    detail: str = "",
    markers: Mapping[str, Any] | None = None,
    execution_uncertain: bool = False,
    surface: str = "",
    grounded: bool | None = None,
) -> RecoveryRecord:
    """Preserve prior failure conditions: diagnosis is independent of task_outcome."""
    diagnosis = diagnose_recovery(
        engine_code=engine_code,
        detail=detail,
        markers=markers,
        execution_uncertain=execution_uncertain,
    )
    return RecoveryRecord(
        diagnosis=diagnosis,
        task_outcome=task_outcome,
        surface=surface,
        grounded=grounded,
        detail=detail[:240],
    )


def should_auto_retry(
    *,
    execution_uncertain: bool = False,
    side_effecting: bool = True,
    retryable: bool | None = None,
) -> bool:
    """Never auto-retry when a side-effecting op left execution uncertain."""
    if execution_uncertain and side_effecting:
        return False
    if retryable is False:
        return False
    if execution_uncertain:
        return False
    return bool(retryable)


def recover_path_arg(
    candidate: str | None,
    *,
    stated_paths: Sequence[str] = (),
    stated_roots: Sequence[str | Path] = (),
) -> str | None:
    """Arg recovery only within user-stated path/scope. Never invent a workspace path.

    Returns the candidate when it matches a stated path or stays under a stated root.
    Empty scope → None (refuse guess). Escape / absolute outside roots → None.
    """
    raw = str(candidate or "").strip()
    if not raw:
        return None
    stated = [str(p).strip() for p in stated_paths if str(p).strip()]
    roots = [Path(r) for r in stated_roots if str(r).strip()]
    if not stated and not roots:
        return None
    for path in stated:
        if raw == path or Path(raw).as_posix() == Path(path).as_posix():
            return raw
    if not roots:
        return None
    from iris.system.execution_policy import check_path_allowed

    for root in roots:
        decision = check_path_allowed(root, raw, write=False)
        if decision.allowed:
            return raw
    return None


# Future 10-run harness schema (attempt, surface, diagnosis, task_outcome, grounded).
ATTEMPT_RECORD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "FFC-05AttemptRecord",
    "type": "object",
    "required": ["attempt", "surface", "diagnosis", "task_outcome", "grounded"],
    "properties": {
        "attempt": {"type": "integer", "minimum": 1},
        "surface": {"type": "string"},
        "diagnosis": {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "enum": [c.value for c in RecoveryClass]},
            ]
        },
        "task_outcome": {"type": "string", "enum": [o.value for o in TaskOutcome]},
        "grounded": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
    },
    "additionalProperties": True,
}


def write_attempt_stub(
    path: str | Path,
    *,
    attempt: int = 1,
    surface: str = "native+mcp",
    diagnosis: RecoveryClass | None = None,
    task_outcome: TaskOutcome = TaskOutcome.REFUSED,
    grounded: bool | None = None,
) -> Path:
    """Tiny recorder stub under .tmp/ffc-05/ (no live model required)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "attempt": int(attempt),
        "surface": surface,
        "diagnosis": None if diagnosis is None else diagnosis.value,
        "task_outcome": task_outcome.value,
        "grounded": grounded,
        "schema": ATTEMPT_RECORD_SCHEMA["title"],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    schema_path = out.with_name("attempt-record.schema.json")
    if not schema_path.exists():
        schema_path.write_text(
            json.dumps(ATTEMPT_RECORD_SCHEMA, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return out


def recovery_class_values() -> tuple[str, ...]:
    return tuple(c.value for c in RecoveryClass)
