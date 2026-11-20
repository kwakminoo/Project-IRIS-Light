"""pull_model on_progress throttle: verifying (pct None) must not flood."""

from __future__ import annotations

import json
from unittest import mock

from iris.infrastructure.local_vision import pull_model


def _ndjson(ev: dict) -> bytes:
    return (json.dumps(ev) + "\n").encode("utf-8")


class _FakePullResp:
    """urlopen context manager whose readline yields NDJSON pull events."""

    def __init__(self, lines: list[bytes]) -> None:
        self._it = iter(lines)

    def readline(self) -> bytes:
        try:
            return next(self._it)
        except StopIteration:
            return b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main() -> None:
    verifying_n = 40
    verifying_status = "verifying sha256 digest"
    lines: list[bytes] = [
        _ndjson({"status": verifying_status}) for _ in range(verifying_n)
    ]
    # Distinct status-only events (no total) — one emit each when status changes.
    distinct_statuses = ["pulling manifest", "pulling config", "verifying digest"]
    for st in distinct_statuses:
        lines.append(_ndjson({"status": st}))
    # Download: same pct twice then next pct — emit only when integer pct changes.
    for done in (10, 10, 25, 25, 50, 100):
        lines.append(
            _ndjson(
                {
                    "status": "downloading",
                    "total": 100,
                    "completed": done,
                }
            )
        )

    calls: list[tuple[str, int | None]] = []

    def on_progress(status: str, pct: int | None) -> None:
        calls.append((status, pct))

    with mock.patch(
        "iris.infrastructure.local_vision.urlopen",
        return_value=_FakePullResp(lines),
    ):
        err = pull_model("http://127.0.0.1:11434", "stub:tag", on_progress=on_progress)
    assert err is None, err

    verifying_emits = [c for c in calls if c[0] == verifying_status and c[1] is None]
    assert len(verifying_emits) <= 1, (
        f"identical verifying status must not re-emit: "
        f"{len(verifying_emits)} calls for {verifying_n} identical lines"
    )

    for st in distinct_statuses:
        n = sum(1 for c in calls if c[0] == st and c[1] is None)
        assert n == 1, f"status-only {st!r} expected 1 emit, got {n}"

    pct_emits = [c[1] for c in calls if c[1] is not None]
    assert pct_emits == [10, 25, 50, 100], (
        f"pct must emit on integer change only, got {pct_emits}"
    )

    print("pull_progress_throttle self-check ok")


if __name__ == "__main__":
    main()
