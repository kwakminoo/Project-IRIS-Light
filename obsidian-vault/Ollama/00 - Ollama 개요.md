# Ollama 개요

> Source: https://docs.ollama.com/  
> 정리일: 2026-07-20

## 소개

Ollama는 **오픈 모델**을 로컬 또는 클라우드에서 실행·연동하기 위한 플랫폼입니다. 빠른 시작(quickstart) 후 모델·통합(integration)·API 중 하나를 선택해 앱에 붙일 수 있습니다.

## 모델

| 방식 | 설명 |
|------|------|
| **로컬** | PC에 모델을 받아 오프라인·저지연 실행 |
| **클라우드** | Ollama Cloud에서 더 큰 모델을 다운로드 없이 실행 |

### 모델 탐색

- [Browse models](https://ollama.com/search) — 채팅, 코딩, 비전, 임베딩, 추론용 모델 검색
- [Cloud models](https://docs.ollama.com/cloud) — 클라우드 전용 대형 모델

## 다음 단계

1. **Integrations** — 에디터·에이전트·어시스턴트에 Ollama 연결  
   → [[01 - Integrations]]
2. **First API request** — 로컬/클라우드 Base URL과 `curl` 예제  
   → [[02 - API Introduction]]
3. **라이브러리** — [Python](https://github.com/ollama/ollama-python), [JavaScript](https://github.com/ollama/ollama-js)

## Iris Light와의 관계

Iris Light는 Ollama를 **ModelPort**로 사용합니다.

- 기본 엔드포인트: `http://127.0.0.1:11434/v1` (OpenAI 호환)
- 클라우드 모델: `-cloud` / `:cloud` 접미사 모델 ID
- UI에서 모델 선택·채팅·thinking 스트림 표시

## 커뮤니티

- [Discord](https://discord.gg/ollama)
- [Reddit — r/ollama](https://reddit.com/r/ollama)

## 문서 인덱스

전체 문서 목록: https://docs.ollama.com/llms.txt
