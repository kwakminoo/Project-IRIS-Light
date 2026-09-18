"""archify CLI 래퍼 — typed JSON IR → 자기완결 HTML 다이어그램.

ponytail: 서브프로세스 1회 호출이 전부다. 스키마·레이아웃 검증은 archify가 하므로
IR을 여기서 다시 검증하지 않고 `diagnostics`를 가공 없이 넘긴다 (모델의 자기수정 입력).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from iris.system.node_runtime import is_node_ready, node_executable
from iris.system.win_subprocess import no_window_kwargs

KINDS = ("architecture", "workflow", "sequence", "dataflow", "lifecycle")

CLI_PATH = Path(__file__).resolve().parents[2] / "integrations" / "archify" / "bin" / "archify.mjs"
OUTPUT_DIR = Path.home() / ".iris-light" / "runtime" / "diagrams"

_SLUG_STRIP = re.compile(r"[^a-z0-9가-힣]+")


def _slug(title: str) -> str:
    s = _SLUG_STRIP.sub("-", (title or "").strip().lower()).strip("-")
    return (s or "diagram")[:48]


def _remote_brands(node: Any) -> list[str]:
    """brand 값에 URL이 있으면 archify가 로고를 원격 fetch한다 — 오프라인 전제를 깬다."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "brand" and isinstance(value, str) and value.startswith(("http://", "https://")):
                found.append(value)
            else:
                found.extend(_remote_brands(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_remote_brands(item))
    return found


def _diag(code: str, message: str) -> list[dict[str, Any]]:
    return [{"code": code, "severity": "error", "message": message}]


def render_diagram(
    kind: str,
    ir: dict[str, Any],
    *,
    title: str = "",
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    """archify deliver 1회. 반환: ok / html_path / diagnostics / error.

    출력은 항상 `~/.iris-light/runtime/diagrams/` 아래이며 project_root에는 쓰지 않는다.
    """
    if kind not in KINDS:
        return {
            "ok": False,
            "error": f"unknown kind {kind!r} (expected one of {', '.join(KINDS)})",
            "diagnostics": _diag("input/kind", f"unknown diagram kind {kind!r}"),
        }
    if not isinstance(ir, dict) or not ir:
        return {
            "ok": False,
            "error": "ir must be a non-empty JSON object",
            "diagnostics": _diag("input/ir", "ir must be a non-empty JSON object"),
        }
    if not CLI_PATH.is_file():
        return {
            "ok": False,
            "error": f"archify CLI not found: {CLI_PATH}",
            "diagnostics": _diag("runtime/cli-missing", str(CLI_PATH)),
        }
    node_ok, node_detail = is_node_ready(min_major=22)
    if not node_ok:
        return {"ok": False, "error": node_detail, "diagnostics": _diag("runtime/node", node_detail)}
    brands = _remote_brands(ir)
    if brands:
        message = (
            "brand URL은 원격 로고 조회를 유발하므로 허용하지 않습니다 "
            f"({brands[0]}). 내장 brand 이름을 쓰거나 brand를 생략하십시오."
        )
        return {"ok": False, "error": message, "diagnostics": _diag("input/brand-url", message)}

    slug = _slug(title or str((ir.get("meta") or {}).get("title") or ""))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ir_path = OUTPUT_DIR / f"{slug}.{kind}.json"
    html_path = OUTPUT_DIR / f"{slug}.{kind}.html"
    ir_path.write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        node_executable(),
        str(CLI_PATH),
        "deliver",
        kind,
        str(ir_path),
        str(html_path),
        "--quality",
        "showcase",
        "--json",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            **no_window_kwargs(),
        )
    except subprocess.TimeoutExpired:
        message = f"archify deliver timed out after {timeout_sec:.0f}s"
        return {"ok": False, "error": message, "diagnostics": _diag("runtime/timeout", message)}

    try:
        report = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        return {
            "ok": False,
            "error": f"archify returned unparseable output: {tail}",
            "diagnostics": _diag("runtime/unparseable", tail),
        }

    if not report.get("ok"):
        return {
            "ok": False,
            "error": str(report.get("error") or "archify deliver failed"),
            "diagnostics": report.get("diagnostics") or [],
            "stage": report.get("stage"),
        }
    return {
        "ok": True,
        "kind": kind,
        "html_path": str(html_path),
        "ir_path": str(ir_path),
        "bytes": int((report.get("artifact") or {}).get("bytes") or 0),
        "validation": report.get("validation") or {},
        "diagnostics": [],
    }
