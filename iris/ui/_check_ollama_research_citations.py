"""Ollama에 자료조사형 질문 10개 → Sources/인용 칩 파이프라인 검증."""

from __future__ import annotations

import json
import re
import sys
import urllib.request

from iris.core.chat_citations import collect_and_tokenize_citations, iris_message_to_chat_html

QUESTIONS = [
    "2024년 노벨 물리학상 수상자는 누구인가요?",
    "파이썬 3.13의 주요 변경점 3가지만 알려줘.",
    "JWST 미션 개요를 한 문단으로.",
    "한국 최저임금 최근 고시 관련 요약.",
    "Rust Edition 2024 요지.",
    "OpenAI 최근 모델 발표 중 하나 요약.",
    "IPCC AR6 핵심 메시지 한 줄.",
    "PostgreSQL 17 주요 기능 2개.",
    "WHO 팬데믹 대비 관련 최근 동향 한 줄.",
    "Apple M4 칩 공개 요지.",
]

SYS = (
    "Answer briefly in Korean. You MUST end with a Sources section using markdown links "
    "like [title](https://official-url). Include at least one real https URL per answer "
    "(official docs/org pages are fine)."
)

_URL = re.compile(r"https?://")
_MD = re.compile(r"\[[^\]]*\]\(https?://[^)]+\)")
MODEL = "gemma4:e2b"
BASE = "http://127.0.0.1:11434/v1/chat/completions"


def chat(q: str) -> str:
    payload = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYS},
                {"role": "user", "content": q},
            ],
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        BASE,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")


def main() -> int:
    results: list[dict] = []
    for i, q in enumerate(QUESTIONS, 1):
        print(f"--- Q{i}/10 ---", q, flush=True)
        try:
            text = chat(q).strip()
        except Exception as exc:  # noqa: BLE001
            print("ERR", exc, flush=True)
            results.append({"n": i, "err": str(exc)})
            continue
        _tok, src = collect_and_tokenize_citations(text)
        html = iris_message_to_chat_html(text)
        row = {
            "n": i,
            "chars": len(text),
            "urls": bool(_URL.search(text)),
            "md": bool(_MD.search(text)),
            "source_count": len(src),
            "chip_footer": ("SOURCES" in html and "href=" in html),
            "preview": text[:240].replace("\n", " "),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    summary = {
        "answered": sum(1 for r in results if "source_count" in r),
        "with_sources": sum(1 for r in results if r.get("source_count", 0) > 0),
        "with_chips": sum(1 for r in results if r.get("chip_footer")),
        "errors": sum(1 for r in results if r.get("err")),
    }
    print("SUMMARY", summary, flush=True)
    if summary["with_chips"] < 1:
        print("FAIL: no citation chips from any answer", file=sys.stderr)
        return 2
    for r in results:
        if r.get("source_count", 0) > 0 and not r.get("chip_footer"):
            print("FAIL chip missing", r.get("n"), file=sys.stderr)
            return 3
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
