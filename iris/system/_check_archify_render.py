"""archify_render 자검 — Node 미설치 명시 실패 / IR 1건 HTML 생성 / 깨진 IR의 diagnostics.

조용한 통과 차단이 목적이다. 깨진 IR이 ok로 통과하거나 diagnostics가 비면 실패한다.
"""

from __future__ import annotations

import json

from iris.system.archify_render import CLI_PATH, KINDS, OUTPUT_DIR, render_diagram
from iris.system.node_runtime import is_node_ready

# 최소 architecture IR — integrations/archify/schemas/architecture.schema.json 기준.
IR: dict = {
    "schema_version": 1,
    "diagram_type": "architecture",
    "meta": {"title": "Iris self check", "quality_profile": "showcase", "viewBox": [1120, 640]},
    # architecture는 layout.mode 생략 시 pos/size를 직접 줘야 한다 (free placement).
    "components": [
        {"id": "chat", "label": "IRIS Chat", "type": "frontend", "pos": [80, 280], "size": [180, 70]},
        {"id": "control", "label": "Control Surface", "type": "backend", "pos": [420, 280], "size": [200, 70]},
        {"id": "ide", "label": "IRIS IDE", "type": "backend", "pos": [780, 280], "size": [180, 70]},
    ],
    "connections": [
        {"from": "chat", "to": "control", "label": "invoke"},
        {"from": "control", "to": "ide", "label": "bridge"},
    ],
}


def _check_inputs_rejected() -> None:
    bad_kind = render_diagram("piechart", IR)
    assert not bad_kind["ok"] and bad_kind["diagnostics"], bad_kind
    empty = render_diagram("architecture", {})
    assert not empty["ok"] and empty["diagnostics"], empty

    branded = json.loads(json.dumps(IR))
    branded["components"][0]["brand"] = "https://example.com/logo.svg"
    remote = render_diagram("architecture", branded)
    assert not remote["ok"], "brand URL은 원격 fetch를 유발하므로 거절해야 함"
    assert remote["diagnostics"][0]["code"] == "input/brand-url", remote


def _check_render_and_diagnostics() -> None:
    ok = render_diagram("architecture", IR, title="Iris self check")
    assert ok["ok"], f"정상 IR 렌더 실패: {ok}"
    html = OUTPUT_DIR / "iris-self-check.architecture.html"
    assert str(html) == ok["html_path"], ok["html_path"]
    assert html.is_file() and html.stat().st_size > 10_000, ok
    body = html.read_text(encoding="utf-8", errors="replace")
    assert "<svg" in body, "SVG가 없는 산출물"
    assert "http://cdn" not in body and "https://cdn" not in body, "외부 CDN 참조 발견"
    assert ok["validation"].get("errors") == 0, ok["validation"]

    broken = json.loads(json.dumps(IR))
    broken["connections"][0]["to"] = "ghost-node"
    bad = render_diagram("architecture", broken, title="Iris self check broken")
    assert not bad["ok"], "존재하지 않는 대상을 가리키는 IR이 통과했음"
    assert bad["diagnostics"], "diagnostics가 비어 있음 — 모델이 자기수정할 수 없음"
    assert "ghost-node" in json.dumps(bad["diagnostics"], ensure_ascii=False), bad["diagnostics"]


def main() -> int:
    assert CLI_PATH.is_file(), f"vendored archify CLI 없음: {CLI_PATH}"
    for kind in KINDS:
        schema = CLI_PATH.parents[1] / "schemas" / f"{kind}.schema.json"
        assert schema.is_file(), f"스키마 누락: {schema}"

    node_ok, node_detail = is_node_ready(min_major=22)
    if not node_ok:
        # 명시적 실패 — Node 없이 조용히 통과시키지 않는다.
        print(f"archify render FAIL: {node_detail}")
        return 1

    _check_inputs_rejected()
    _check_render_and_diagnostics()
    print(f"archify render ok ({node_detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
