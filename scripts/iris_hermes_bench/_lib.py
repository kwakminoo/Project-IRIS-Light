"""Shared helpers for Iris vs Hermes capability bench."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = Path(__file__).resolve().parent
CASES_DIR = BENCH_DIR / "cases"
TEMPLATE = BENCH_DIR / "templates" / "hermes_bench.yaml"
DEFAULTS_PATH = BENCH_DIR / "manifest.defaults.json"
WORK_ROOT = ROOT / ".iris_light_test_tmp" / "iris_hermes_bench"
PHASE_FILES = {
    1: "phase1_smoke.jsonl",
    2: "phase2_coding.jsonl",
    3: "phase3_web.jsonl",
    4: "phase4_product.jsonl",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_defaults() -> dict[str, Any]:
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


def expand_path(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def load_cases(phase: int) -> list[dict[str, Any]]:
    path = CASES_DIR / PHASE_FILES[phase]
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iris_endpoint() -> tuple[str, str] | None:
    d = Path.home() / ".iris-light"
    port_p, tok_p = d / "control_port", d / "control_token"
    if not port_p.is_file() or not tok_p.is_file():
        return None
    port = port_p.read_text(encoding="utf-8").strip()
    token = tok_p.read_text(encoding="utf-8").strip()
    if not port or not token:
        return None
    return f"http://127.0.0.1:{port}", token


def iris_invoke(action: str, args: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    ep = iris_endpoint()
    if ep is None:
        return {"ok": False, "error": "control endpoint missing"}
    base, token = ep
    body = json.dumps({"action": action, "args": args or {}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base + "/v1/invoke",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"http": resp.status, **json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return {"http": exc.code, "ok": False, **parsed}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def ollama_has_model(model: str) -> tuple[bool, str]:
    try:
        body = json.dumps({"model": model}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/show",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        caps = data.get("capabilities") or []
        return True, f"ok caps={caps}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def grade_text(grade: dict[str, Any], text: str) -> tuple[bool | None, str]:
    kind = grade.get("kind")
    t = text or ""
    if kind in ("swe_placeholder", "gaia_placeholder"):
        return None, "placeholder"
    if kind == "manual":
        return None, "manual"
    if kind == "product_effect":
        # Scored only via grade_product_effect (needs before/after + arm).
        return None, "product_effect"
    if kind == "exact":
        want = str(grade.get("value", "")).strip()
        ok = t.strip() == want
        return ok, "exact"
    if kind == "contains":
        needles = grade.get("needles") or []
        ok = any(n in t for n in needles)
        return ok, "contains"
    if kind == "regex":
        pat = grade.get("pattern") or ""
        ok = re.search(pat, t, re.I | re.S) is not None
        return ok, "regex"
    return None, f"unknown_grade:{kind}"


def iris_db_path() -> Path:
    return Path.home() / ".iris-light" / "iris_light.db"


def iris_max_message_id() -> int:
    import sqlite3

    path = iris_db_path()
    if not path.is_file():
        return 0
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    try:
        row = con.execute("SELECT COALESCE(MAX(id), 0) FROM chat_messages").fetchone()
        return int(row[0] or 0)
    finally:
        con.close()


def iris_assistant_after(min_id: int) -> tuple[int, str] | None:
    """Return first assistant row with id > min_id, if any."""
    import sqlite3

    path = iris_db_path()
    if not path.is_file():
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    try:
        row = con.execute(
            """
            SELECT id, content FROM chat_messages
             WHERE role = 'assistant' AND id > ?
             ORDER BY id ASC LIMIT 1
            """,
            (int(min_id),),
        ).fetchone()
        if row is None:
            return None
        return int(row[0]), str(row[1] or "")
    finally:
        con.close()


def _wiki_titles_matching(title: str) -> list[str]:
    resp = iris_invoke("wiki.search", {"query": title}, timeout=30.0)
    hits = (resp.get("result") or {}).get("hits") or []
    out: list[str] = []
    for hit in hits:
        t = str(hit.get("title") or "")
        if title in t:
            out.append(t)
    return out


def _session_titles() -> list[str]:
    resp = iris_invoke("chat.list_sessions", {}, timeout=30.0)
    sessions = (resp.get("result") or {}).get("sessions") or []
    return [str(s.get("title") or "") for s in sessions]


def _recent_folders_text() -> str:
    path = Path.home() / ".iris-light" / "ide-recent-folders.json"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _last_run_text(project_root: Path | None = None) -> str:
    root = project_root or ROOT
    path = root / ".iris" / "last_run.log"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def snapshot_product(grade: dict[str, Any]) -> dict[str, Any]:
    """Capture observable product state used by product_effect probes."""
    probe = str(grade.get("probe") or "")
    snap: dict[str, Any] = {"probe": probe}
    if probe == "wiki_note":
        title = str(grade.get("title") or "")
        snap["titles"] = _wiki_titles_matching(title)
    elif probe == "ide_folder":
        snap["recent"] = _recent_folders_text()
    elif probe == "project_run":
        snap["last_run"] = _last_run_text()
    elif probe == "session_title":
        title = str(grade.get("title") or "bench-phase4")
        snap["titles"] = _session_titles()
        snap["want"] = title
    elif probe == "tool_claim":
        snap["ok"] = True
    return snap


def _text_claims_success(text: str) -> bool:
    t = text or ""
    return bool(
        re.search(
            r"(성공|완료|열었습니다|만들었습니다|생성했|실행했|wrote|created|opened|done)",
            t,
            re.I,
        )
    )


def _text_denies_tools(text: str) -> bool:
    t = text or ""
    return bool(
        re.search(
            r"(없|불가|cannot|can't|unable|no (iris )?tools|도구가 없|로드되지)",
            t,
            re.I,
        )
    )


def _text_lists_iris_tools(text: str) -> bool:
    t = (text or "").lower()
    keys = ("wiki", "ide.", "project.run", "iris-control", "iris_control", "companion")
    return sum(1 for k in keys if k in t) >= 2


def effect_present(
    grade: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    text: str,
) -> tuple[bool, str]:
    """Return (effect_happened, detail)."""
    probe = str(grade.get("probe") or "")
    if probe == "wiki_note":
        title = str(grade.get("title") or "")
        body = str(grade.get("body") or "")
        before_n = set(before.get("titles") or [])
        after_titles = list(after.get("titles") or [])
        gained = [t for t in after_titles if t not in before_n and title in t]
        if gained:
            return True, f"wiki_title:{gained[0]}"
        # Search may lag; also accept body hit in excerpts via re-search raw.
        resp = iris_invoke("wiki.search", {"query": body or title}, timeout=30.0)
        for hit in (resp.get("result") or {}).get("hits") or []:
            blob = json.dumps(hit, ensure_ascii=False)
            if title in blob and (not body or body in blob):
                return True, "wiki_search_hit"
        return False, "wiki_missing"
    if probe == "ide_folder":
        b = str(before.get("recent") or "")
        a = str(after.get("recent") or "")
        if a and a != b:
            return True, "recent_folders_changed"
        return False, "recent_folders_unchanged"
    if probe == "project_run":
        needle = str(grade.get("needle") or "42")
        b = str(before.get("last_run") or "")
        a = str(after.get("last_run") or "")
        if needle in a and needle not in b:
            return True, "last_run_needle"
        if needle in a and a != b:
            return True, "last_run_updated"
        return False, "last_run_missing"
    if probe == "session_title":
        want = str(grade.get("title") or after.get("want") or "bench-phase4")
        after_titles = list(after.get("titles") or [])
        # Exact title only. Auto titles like "bench-phase4 채팅 세션 생성" must not pass.
        if any(want == t for t in after_titles):
            return True, f"session:{want}"
        return False, "session_title_missing"
    if probe == "tool_claim":
        # Effect = model claims Iris desktop tools are available.
        return _text_lists_iris_tools(text) and not _text_denies_tools(text), "tool_claim_text"
    return False, f"unknown_probe:{probe}"


def grade_product_effect(
    grade: dict[str, Any],
    *,
    arm: str,
    text: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    """Score product_effect for one arm. Expect present|absent per arm."""
    expect_map = grade.get("expect") or {}
    expect = str(expect_map.get(arm) or "").strip().lower()
    happened, detail = effect_present(grade, before, after, text)
    meta = {
        "expect": expect,
        "effect": happened,
        "detail": detail,
        "claimed_success": _text_claims_success(text),
        "denied_tools": _text_denies_tools(text),
    }
    if expect == "present":
        ok = happened
        return ok, "product_effect:present", meta
    if expect == "absent":
        # Pass if no side effect. Extra fail if text boasts success without effect.
        if happened:
            return False, "product_effect:absent_but_effect", meta
        if _text_claims_success(text) and str(grade.get("probe")) != "tool_claim":
            return False, "product_effect:hallucinated_success", meta
        return True, "product_effect:absent", meta
    if expect == "deny_tools":
        ok = _text_denies_tools(text) and not _text_lists_iris_tools(text)
        return ok, "product_effect:deny_tools", meta
    if expect == "list_tools":
        ok = _text_lists_iris_tools(text)
        return ok, "product_effect:list_tools", meta
    return False, f"product_effect:bad_expect:{expect}", meta
