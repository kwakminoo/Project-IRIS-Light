# Iris Light — API 명세서

> 상세본: `docs/api/API-명세서.md` · IA: `docs/ia/IA.md`  
> Generated-at: 2026-07-22

## 연결

```
Iris (.env: IRIS_*) → Hermes :8642 (.env: API keys)
                        ├─ Ollama :11434 (기본 LLM)
                        ├─ SerpApi (web_search, engine=)
                        ├─ Firecrawl / Exa (extract·보조 검색)
                        ├─ Naver Search (스킬, 키만 보관 가능)
                        └─ Google Gemini (옵션 provider)
```

## Hermes 스킬 (iris-apis)

| name | API |
|------|-----|
| `serpapi` | SerpApi (`engine=`) |
| `exa` | Exa |
| `firecrawl` | Firecrawl |
| `google-gemini` | Google AI Studio |
| `naver-search` | 네이버 검색 |

## Iris Control (Hermes → Iris UI)

- HTTP: `127.0.0.1:8765` + Bearer token (`~/.iris-light/control_token`)
- MCP: `iris.mcp.iris_control_stdio` → `iris_get_state` / `iris_get_catalog` / `iris_invoke`
- Skills: `iris-work-start`, `iris-work-end`, `iris-session-status`
- 가이드: `integrations/hermes-skills/README.md`

## SerpApi

- Base: `https://serpapi.com/search.json`
- 엔진: `engine=google|google_news|yahoo_images|bing|…` (엔드포인트는 하나)
- 설정: `web.search_backend: serpapi`
- Wiki: [[01 - 엔진 카탈로그]]

관련: [[프로젝트 개요]] · [[05 - API Server와 Iris Light 연동]] · [[01 - 엔진 카탈로그]]
