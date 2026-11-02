# Iris Agent 개요

> 정리일: 2026-10-28  
> 업스트림 크레딧: Nous Research Hermes Agent (MIT) — NOTICE 참고  
> 제품 정본: `docs/domain.md`

## 한 줄 정의

**Iris Agent**는 Iris Light가 **흡수·소유한 에이전트 코어**다.  
루프·툴·스킬·메모리·MCP 호스트를 제품 홈에서 돌린다. Hermes를 바깥에 두는 wrap 구조가 아니다.

## Iris Light와의 관계

```
[Iris Light UI]
       │
       ▼
[Iris Agent — InternalSidecar 기본]
       ├─ native tools (IrisAgentToolRegistry seed)
       ├─ 스킬 (iris-control 등)
       ├─ (비시드 compat) Control :8765 / MCP
       └─ LLM ──▶ Ollama
```

| Iris Light | Iris Agent |
|------------|------------|
| HUD·채팅·워크스페이스 UI | NL → 도구 실행 |
| 채팅 워커 / `iris/engine` | InternalSidecar (기본) |
| 설정·supervisor | 홈 `~/.iris-light/agent` |

관련: [[05 - API와 Iris Light 연동]]

## 설치 (요약)

Iris 기동·Setup Protocol이 핀된 런타임을 제품 홈에 맞춘다.  
별도 `hermes` CLI로 `%LOCALAPPDATA%\hermes`에 깔아 쓰는 경로가 **활성 홈이 아니다**.

자세히: [[01 - 설치와 설정]]

## 핵심 특징

| 영역 | 내용 |
|------|------|
| **홈** | `IRIS_AGENT_HOME` 또는 `~/.iris-light/agent` |
| **기본 실행** | InternalSidecar (`shared_engine`) |
| **옵션** | ExternalGateway `:8642` |
| **스킬** | `integrations/hermes-skills/iris-control/*` → 제품 홈 sync |
| **정본 대화** | Iris SQLite (`~/.iris-light/iris_light.db`) |

## 관련 노트

- [[01 - 설치와 설정]]
- [[02 - 핵심 기능 (도구·메모리·스킬)]]
- [[03 - MCP 연동]]
- [[04 - 자동화와 Gateway]]
- [[05 - API와 Iris Light 연동]]
- [[06 - 이메일과 생산성 스킬]]
- [[07 - Skills 카탈로그 요약]]
