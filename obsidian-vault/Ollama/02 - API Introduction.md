# Ollama API Introduction

> Source: https://docs.ollama.com/api/introduction  
> 정리일: 2026-07-20

## 소개

Ollama **API**로 모델을 실행하고 상호작용합니다. 설치 후 Ollama가 떠 있으면 HTTP로 바로 호출할 수 있습니다.

## Base URL

### 로컬

설치 후 기본 API 주소:

```
http://localhost:11434/api
```

OpenAI 호환 엔드포인트(Iris Light 기본):

```
http://localhost:11434/v1
```

### 클라우드 (ollama.com)

클라우드 모델 실행 시 동일 API 형식:

```
https://ollama.com/api
```

인증이 필요할 수 있으며, 환경 변수 `OLLAMA_API_KEY`를 사용합니다.

## 예제 요청

Ollama 실행 중 `curl`로 generate API 호출:

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "gemma4",
  "prompt": "Why is the sky blue?"
}'
```

### 채팅 API

대화형 메시지 생성: `POST /api/chat`  
문서: https://docs.ollama.com/api/chat

## 공식 라이브러리

| 언어 | 저장소 |
|------|--------|
| Python | https://github.com/ollama/ollama-python |
| JavaScript | https://github.com/ollama/ollama-js |

커뮤니티 라이브러리 목록: [Ollama GitHub README](https://github.com/ollama/ollama?tab=readme-ov-file#libraries-1)

## 버전 정책

- API는 **엄격한 버전 번호는 없음**
- **안정적·하위 호환**을 목표로 유지
- 폐기(deprecation)는 드물며 [릴리스 노트](https://github.com/ollama/ollama/releases)에 공지

## Iris Light 구현 참고

`iris/infrastructure/ollama_client.py`:

| 기능 | 엔드포인트/방식 |
|------|----------------|
| 모델 목록 | `GET /api/tags` (로컬), `https://ollama.com/api/tags` (클라우드 카탈로그) |
| 채팅 스트림 | OpenAI 호환 `/v1/chat/completions` |
| Thinking | 스트림 청크에서 reasoning 필드 처리 |

## 관련 API 문서

- [Streaming](https://docs.ollama.com/api/streaming)
- [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [Tool calling](https://docs.ollama.com/capabilities/tool-calling)
- [Errors](https://docs.ollama.com/api/errors)

관련: [[00 - Ollama 개요]] · [[01 - Integrations]]
