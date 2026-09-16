# Iris Light — API 명세서

> 상세본: `docs/api/API-명세서.md` · IA: `docs/ia/IA.md`  
> Generated-at: 2026-07-22 · Updated-at: 2026-08-25

## 연결

```
IRIS (.env: IRIS_*) → Hermes :8642 (.env: API keys)
                        ├─ Ollama :11434 (기본 LLM)
                        ├─ SerpApi / Firecrawl / Exa / Naver
                        └─ MCP iris-control → IRIS Control :8765
음성(옵션): Voice Runtime :18765
```

## Hermes 스킬

### 저장소 동봉 — `iris-control/*`

| name | 역할 |
|------|------|
| `iris-work-start` / `iris-work-end` | 작업 세션 |
| `iris-session-status` | 상태 조회 |
| `iris-vibe-code` | 바이브코딩 |
| `iris-emulator` / `iris-mobile-mcp` | 모바일 |
| `iris-calendar` / `iris-learning` | 캘린더·화면학습 |

### Hermes 로컬 — `iris-apis/*` (`%LOCALAPPDATA%\hermes\skills\`)

| name | API |
|------|-----|
| `serpapi` | SerpApi (`engine=`) |
| `exa` / `firecrawl` | Exa / Firecrawl |
| `google-gemini` | Google AI Studio |
| `naver-search` | 네이버 검색 |

## Iris Control (Hermes → Iris UI)

- HTTP: `127.0.0.1:8765` + Bearer token (`~/.iris-light/control_token`)
- MCP: `iris.mcp.iris_control_stdio` → `iris_get_state` / `iris_get_catalog` / `iris_invoke`
- 가이드: `integrations/hermes-skills/README.md`

## SerpApi

- Base: `https://serpapi.com/search.json`
- 엔진: `engine=google|google_news|yahoo_images|bing|…`
- Wiki: [[01 - 엔진 카탈로그]]
