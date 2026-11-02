"""제품 문서가 Iris Agent 정본을 쓰는지 자검.

실행: .venv\\Scripts\\python.exe -m iris.ui._check_iris_agent_product_docs_brand

활성 홈으로 `%LOCALAPPDATA%\\hermes`를 쓰거나 Iris가 Hermes를 감싼다고 쓰면 실패.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRODUCT_DOCS = (
    "docs/domain.md",
    "docs/ia/IA.md",
    "docs/api/API-명세서.md",
    "docs/guides/extending-iris.md",
    "docs/IRIS_개발문서.md",
)

MUST_CONTAIN = (
    "Iris Agent",
    "~/.iris-light/agent",
)

# 활성 홈·구 아키텍처 주장. 면책 문구(「구 …는 활성 홈 아님」)는 허용.
BANNED_ACTIVE = (
    "감싸는",
    "감싸는 데스크톱",
    "소유하지 않음",
)

ACTIVE_HOME_NEEDLE = r"%LOCALAPPDATA%\hermes"


def _is_disclaimer(line: str) -> bool:
    return "활성 홈 아님" in line or "활성 홈이 아니다" in line


def main() -> None:
    hits: list[str] = []
    for rel in PRODUCT_DOCS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        for needle in MUST_CONTAIN:
            if needle not in text:
                hits.append(f"{rel}: missing {needle!r}")
        if "InternalSidecar" not in text and "InternalSidecar" not in rel:
            # API 명세는 엔진 이름을 약하게만 써도 되나, domain/IA/개발문서는 필수에 가깝다
            if rel in {
                "docs/domain.md",
                "docs/ia/IA.md",
                "docs/IRIS_개발문서.md",
                "docs/guides/extending-iris.md",
            }:
                hits.append(f"{rel}: missing 'InternalSidecar'")
        for banned in BANNED_ACTIVE:
            if banned in text:
                hits.append(f"{rel}: banned {banned!r}")
        for i, line in enumerate(text.splitlines(), 1):
            if ACTIVE_HOME_NEEDLE in line and not _is_disclaimer(line):
                hits.append(f"{rel}:{i}: active-home {ACTIVE_HOME_NEEDLE!r}")

    assert not hits, "product docs brand failures:\n" + "\n".join(hits)
    print("iris_agent_product_docs_brand ok", len(PRODUCT_DOCS), "files")


if __name__ == "__main__":
    main()
