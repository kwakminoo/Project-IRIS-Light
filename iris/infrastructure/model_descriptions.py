"""Ollama 모델 짧은 설명(한국어) — 모델 콤보 툴팁·현재 모델 표시·변경 안내용.

출처: ollama.com 각 모델 라이브러리 페이지 공식 설명 + `/api/show` capabilities.
obsidian-vault/Ollama/03 - 클라우드 모델 카탈로그.md 와 동기화해 관리한다.
ponytail: 카탈로그가 크지 않아 정적 매핑으로 충분. 신규 모델은 여기에 한 줄 추가.
"""

from __future__ import annotations

# (부분 문자열 키, 설명) — 위에서부터 먼저 매칭. 구체 모델명을 계열 총칭보다 앞에 둔다.
_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    ("kimi-k2.7-code", "Kimi K2.7 Code — 코딩 특화 에이전트, 장기 코딩+thinking 토큰 절감 · 이미지·도구·추론"),
    ("kimi-k2.6", "Kimi K2.6 — 장기 코딩·자율 실행·작업 오케스트레이션 · 이미지·도구·추론"),
    ("kimi-k2.5", "Kimi K2.5 — 네이티브 멀티모달 에이전트(instant/thinking) · 이미지·도구·추론"),
    ("kimi-k2", "Moonshot Kimi K2 — 초대형 멀티모달 코딩 에이전트"),
    ("qwen3.5", "Qwen 3.5 — 다국어(201개)·멀티모달·코딩·에이전트 전방위 상위 · 이미지·도구·추론"),
    ("deepseek-v4-flash", "DeepSeek V4 Flash — 1M 초장문 컨텍스트, 효율적 추론 · 도구·추론"),
    ("deepseek-v4-pro", "DeepSeek V4 Pro — 프런티어급 MoE, 3가지 추론 모드 · 도구·추론"),
    ("deepseek-v4", "DeepSeek V4 — 대형 MoE, 강력한 추론·코딩"),
    ("deepseek", "DeepSeek — 코딩·추론 강점"),
    ("glm-5.2", "GLM-5.2 — 장기 과제(long-horizon) 플래그십, 1M 컨텍스트 · 코딩·에이전트"),
    ("glm-5.1", "GLM-5.1 — 에이전틱 코딩 특화(SWE-Bench Pro SOTA) · 도구·추론"),
    ("glm", "Z.ai GLM — 범용·코딩·에이전트"),
    ("gpt-oss", "OpenAI gpt-oss — 강력한 추론·에이전트, 오픈웨이트(Apache 2.0) · 도구·추론"),
    ("minimax-m3", "MiniMax M3 — 코딩·에이전트 프런티어 + 네이티브 멀티모달, 대용량 컨텍스트"),
    ("minimax-m2.7", "MiniMax M2.7 — 코딩·에이전트·전문 생산성 · 도구·추론"),
    ("minimax-m2.5", "MiniMax M2.5 — 실무 생산성·코딩 · 도구·추론"),
    ("minimax", "MiniMax — 코딩·에이전트·생산성"),
    ("mistral-large-3", "Mistral Large 3 — 프로덕션·엔터프라이즈 범용 멀티모달(추론 모드 없음) · 이미지·도구"),
    ("mistral", "Mistral — 범용·코딩"),
    ("nemotron-3-nano", "NVIDIA Nemotron 3 Nano — 경량 효율형 에이전트 · 도구·추론"),
    ("nemotron-3-super", "NVIDIA Nemotron 3 Super — 효율 대비 정확도, 멀티에이전트 · 도구·추론"),
    ("nemotron-3-ultra", "NVIDIA Nemotron 3 Ultra — 고처리량 추론·장기 에이전트 · 도구·추론"),
    ("nemotron", "NVIDIA Nemotron 3 — 효율형 추론·에이전트"),
    ("gemma4", "Google Gemma 4 — 이미지 분석·코딩·추론·에이전트 균형형 멀티모달"),
    ("gemma", "Google Gemma — 경량 멀티모달"),
)


def describe_model(name: str) -> str:
    """모델 런타임/표시 이름 → 짧은 한국어 설명. 매칭 없으면 빈 문자열."""
    n = (name or "").strip().lower()
    if not n:
        return ""
    for suf in ("-cloud", ":cloud"):
        if n.endswith(suf):
            n = n[: -len(suf)]
            break
    for key, desc in _DESCRIPTIONS:
        if key in n:
            return desc
    return ""


if __name__ == "__main__":
    assert describe_model("qwen3.5:397b-cloud").startswith("Qwen 3.5")
    assert describe_model("gemma4:26b").startswith("Google Gemma 4")
    assert describe_model("minimax-m3:cloud").startswith("MiniMax M3")
    assert describe_model("kimi-k2.7-code").startswith("Kimi K2.7 Code")
    assert describe_model("") == ""
    assert describe_model("unknown-model:1b") == ""
    print("model_descriptions self-check ok")
