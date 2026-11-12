"""AI Hub analytics — call samples in user_preferences JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from iris.storage.database import Database

SAMPLES_KEY = "ai_analytics_samples_v1"
SAMPLES_CAP = 500


@dataclass(frozen=True)
class AiCallSample:
    runtime_model: str
    ok: bool
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    ts: str = ""


@dataclass(frozen=True)
class AiAggregateStats:
    requests: int
    success_rate: float
    tokens_in: int
    tokens_out: int
    avg_latency_ms: float


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_sample(raw: object) -> AiCallSample | None:
    if not isinstance(raw, dict):
        return None
    try:
        return AiCallSample(
            runtime_model=str(raw.get("runtime_model") or ""),
            ok=bool(raw.get("ok")),
            latency_ms=float(raw.get("latency_ms") or 0.0),
            tokens_in=int(raw.get("tokens_in") or 0),
            tokens_out=int(raw.get("tokens_out") or 0),
            ts=str(raw.get("ts") or ""),
        )
    except (TypeError, ValueError):
        return None


def load_samples(db: Database, *, limit: int = 500) -> list[AiCallSample]:
    raw = (db.get_preference(SAMPLES_KEY, "") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[AiCallSample] = []
    for item in data:
        sample = _coerce_sample(item)
        if sample is not None:
            out.append(sample)
    cap = max(0, int(limit))
    if cap and len(out) > cap:
        return out[-cap:]
    return out


def record_sample(db: Database, sample: AiCallSample) -> None:
    stamped = sample if sample.ts else AiCallSample(
        runtime_model=sample.runtime_model,
        ok=sample.ok,
        latency_ms=sample.latency_ms,
        tokens_in=sample.tokens_in,
        tokens_out=sample.tokens_out,
        ts=_now_iso(),
    )
    items = load_samples(db, limit=SAMPLES_CAP)
    items.append(stamped)
    if len(items) > SAMPLES_CAP:
        items = items[-SAMPLES_CAP:]
    payload = [asdict(s) for s in items]
    db.set_preference(SAMPLES_KEY, json.dumps(payload, ensure_ascii=False))


def aggregate_stats(samples: list[AiCallSample]) -> AiAggregateStats:
    if not samples:
        return AiAggregateStats(
            requests=0,
            success_rate=0.0,
            tokens_in=0,
            tokens_out=0,
            avg_latency_ms=0.0,
        )
    n = len(samples)
    ok_n = sum(1 for s in samples if s.ok)
    tokens_in = sum(int(s.tokens_in) for s in samples)
    tokens_out = sum(int(s.tokens_out) for s in samples)
    avg_latency = sum(float(s.latency_ms) for s in samples) / n
    return AiAggregateStats(
        requests=n,
        success_rate=ok_n / n,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        avg_latency_ms=avg_latency,
    )
