# Hermes — API Server와 Iris Light 연동

> Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server  
> 정리일: 2026-07-20

## API Server 개요

Hermes를 **OpenAI 호환 HTTP API**로 노출합니다.  
Open WebUI, LobeChat, **Iris Light** 등 `/v1/chat/completions` 클라이언트가 연결 가능.

도구(terminal, web, memory, skills) **전체 toolset**으로 요청 처리.

## Quick Start

### 1) Hermes 측 설정

`~/.hermes/.env`:

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=change-me-local-dev
```

### 2) Gateway 시작

```bash
hermes gateway
```

```
[API Server] API server listening on http://127.0.0.1:8642
```

### 3) curl 테스트

```bash
curl http://127.0.0.1:8642/v1/chat/completions \
  -H "Authorization: Bearer change-me-local-dev" \
  -H "Content-Type: application/json" \
  -d '{"model": "hermes-agent", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## 주요 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | `/v1/chat/completions` | OpenAI Chat Completions (stateless) |
| POST | `/v1/responses` | Responses API (서버측 대화 상태) |
| GET | `/health` | 헬스체크 |

### 스트리밍

`"stream": true` → SSE  
Hermes 전용 이벤트: `hermes.tool.progress` (도구 시작 UX)

Iris Light `HermesChatWorker`가 이 스트림을 수신해 Live Activity·채팅에 표시.

## Iris Light 연동 (코드)

### 설정 (`iris/config/settings.py`)

| 변수 | 기본값 |
|------|--------|
| `IRIS_HERMES_ENABLED` | `1` |
| `IRIS_HERMES_BASE_URL` | `http://127.0.0.1:8642/v1` |
| `IRIS_HERMES_API_KEY` | (비움 → API_SERVER_KEY) |
| `IRIS_HERMES_COMMAND` | `hermes` |

### 클라이언트 (`iris/infrastructure/hermes_client.py`)

- `health_ok()` — gateway 상태
- `set_inference_model(model)` — Iris 모델 선택 → Hermes 동기화
- `stream_chat(model, messages)` — 스트리밍 채팅

### UI (`iris/ui/main_window.py`)

- `IRIS_HERMES_ENABLED=1` → `HermesChatWorker` 사용
- Hermes offline → "gateway 실행 확인" 메시지
- 상태 헤더 HERMES 칩: Connected / Offline

### `.env` 예시 (Iris Light)

```bash
IRIS_HERMES_ENABLED=1
IRIS_HERMES_BASE_URL=http://127.0.0.1:8642/v1
IRIS_HERMES_API_KEY=change-me-local-dev
IRIS_OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
IRIS_OLLAMA_MODEL=gemma4:26b
```

## Provider 스택

```
Iris Chat → Hermes API (:8642)
                → Hermes Agent (tools + skills + MCP)
                    → Ollama (:11434/v1) 또는 OpenRouter 등
```

Hermes setup에서 Ollama를 provider로 지정하면 **Iris 모델 콤보 ↔ Hermes inference model** 동기화.

## Responses API (고급)

`previous_response_id` 또는 `conversation: "my-project"`로 **멀티턴 컨텍스트** 서버 보관.

Iris Light 현재는 Chat Completions + 클라이언트측 `_history` 사용.

## 보안

- `API_SERVER_KEY` 필수 (Bearer)
- CORS: `API_SERVER_CORS_ORIGINS` (브라우저 직접 호출 시)
- 로컬호스트만 바인딩 권장

## 문제 해결

| 증상 | 확인 |
|------|------|
| Iris "Hermes gateway 연결 불가" | `hermes gateway` 실행, `:8642` |
| HERMES Offline | `HermesHealthWorker` → `/health` |
| 모델 불일치 | 설정 저장 후 `_sync_hermes_model` |
| 도구 안 씀 | Hermes chat에서 toolset/MCP 확인 |

관련: [[01 - 설치와 설정]] · [[00 - Hermes Agent 개요]]
