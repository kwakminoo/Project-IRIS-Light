"""활성 .cursor/rules 제품 문구가 Iris Agent인지 자검.

실행: .venv\\Scripts\\python.exe -m iris.ui._check_iris_agent_rules_brand

제품명 Hermes(채팅 착지·iris-control·Core 설치 UI)는 실패.
레거시 checkout `hermes-agent`, 업스트림 이슈 `Hermes #…`, completed 이력 문서 경로는 허용.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / ".cursor" / "rules"

# 제품으로 Hermes를 가리키는 문구 (활성 규칙에서 금지).
BANNED_PRODUCT = (
    re.compile(r"Hermes\s+ON"),
    re.compile(r"Hermes\s+채팅"),
    re.compile(r"#\s*Hermes\s"),
    re.compile(r"Hermes\s+`iris-control`|Hermes\s+iris-control"),
    re.compile(r"Core「Hermes"),
    re.compile(r"\bHermesChatWorker\b"),  # 코드는 IrisAgentChatWorker
)

# 허용: 레거시 경로·업스트림 이슈·이력 문서 파일명.
_ALLOW_LINE = re.compile(
    r"hermes-agent"  # checkout 폴백
    r"|Hermes\s*#\d+"  # 업스트림 이슈
    r"|completed/Hermes"  # 이력 보고서 경로
    r"|헤르메스-"  # 이력 보고서 경로
    r"|nousresearch"
    r"|HERMES_INSTALL"
)


def main() -> None:
    hits: list[str] = []
    old = RULES / "hermes-chat-landing.mdc"
    if old.is_file():
        hits.append("stale rule file still present: hermes-chat-landing.mdc")
    landing = RULES / "iris-agent-chat-landing.mdc"
    if not landing.is_file():
        hits.append("missing iris-agent-chat-landing.mdc")
    else:
        body = landing.read_text(encoding="utf-8")
        if "Iris Agent" not in body:
            hits.append("iris-agent-chat-landing.mdc: missing 'Iris Agent'")
        if "IrisAgentChatWorker" not in body:
            hits.append("iris-agent-chat-landing.mdc: missing IrisAgentChatWorker")

    for path in sorted(RULES.glob("*.mdc")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if not re.search(r"[Hh]ermes|헤르메스", line, re.I):
                continue
            if _ALLOW_LINE.search(line):
                continue
            for pat in BANNED_PRODUCT:
                if pat.search(line):
                    hits.append(f"{rel}:{i}: banned product Hermes: {line.strip()[:100]}")
                    break
            else:
                # Hermes/헤르메스 잔여인데 allow/banned 어느 쪽도 아니면 설명 필요 → 실패
                if re.search(r"\bHermes\b|헤르메스", line):
                    hits.append(f"{rel}:{i}: unexplained Hermes: {line.strip()[:100]}")

        if path.name == "engine-uv-probe-boost.mdc" and "iris-agent" not in text:
            hits.append(f"{rel}: prefer iris-agent checkout path")

    assert not hits, "iris agent rules brand failures:\n" + "\n".join(hits)
    print("iris_agent_rules_brand ok", len(list(RULES.glob('*.mdc'))), "rules")


if __name__ == "__main__":
    main()
