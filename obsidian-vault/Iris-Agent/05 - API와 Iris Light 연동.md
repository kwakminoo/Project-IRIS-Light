# Iris Agent — API와 Iris Light 연동

> 정리일: 2026-10-28  
> 명세: `docs/api/API-명세서.md`

## 기본 경로

Iris 채팅 워커 → **InternalSidecar** (`iris/engine`) → Ollama 추론 + 도구.

OpenAI 호환 HTTP `:8642`는 **옵션**(ExternalGateway)이다.

## 옵션 HTTP Quick Start

제품 홈 `.env` 예:

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=change-me-local-dev
```

베이스: `http://127.0.0.1:8642` · Iris는 `/v1` suffix.

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/chat/completions` | Chat Completions |
| GET | `/health` | 헬스 |

## Control Surface

비시드 역제어: `http://127.0.0.1:8765` (compat).

관련: [[00 - Iris Agent 개요]] · [[03 - MCP 연동]]
