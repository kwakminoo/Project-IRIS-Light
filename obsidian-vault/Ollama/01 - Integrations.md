# Ollama Integrations

> Source: https://docs.ollama.com/integrations  
> 정리일: 2026-07-20

## 개요

Ollama는 **코딩 에이전트**, **개인 어시스턴트**, **에디터**에서 바로 쓸 수 있도록 다양한 통합을 제공합니다.

터미널에서 사용 가능한 통합 목록:

```bash
ollama launch
```

## 터미널 코딩 에이전트

| 통합 | 설명 | 문서 |
|------|------|------|
| **Claude Code** | 도구·비전·웹 검색·긴 컨텍스트를 지원하는 터미널 코딩 에이전트 | [/integrations/claude-code](https://docs.ollama.com/integrations/claude-code) |
| **OpenCode** | 코드 편집·실행·반복 개선을 하는 오픈소스 코딩 에이전트 | [/integrations/opencode](https://docs.ollama.com/integrations/opencode) |

## 어시스턴트 연결

메모리·스킬·메시징 앱 연동이 있는 어시스턴트:

| 통합 | 설명 | 문서 |
|------|------|------|
| **OpenClaw** | 메시징 앱·일상 업무용 개인 어시스턴트 | [/integrations/openclaw](https://docs.ollama.com/integrations/openclaw) |
| **Hermes Agent** | 자기 개선 스킬·메모리·메시징을 갖춘 오픈소스 에이전트 | [/integrations/hermes](https://docs.ollama.com/integrations/hermes) |

### Iris Light ↔ Hermes

Iris Light 도메인 설계상 **Hermes**는 AgentPort 구현체입니다.

- Hermes가 Ollama를 provider로 사용 (`http://127.0.0.1:11434/v1`)
- Iris는 NL→도구 매핑을 직접 구현하지 않고 **세션·UI·스트림**만 담당
- 설정: `IRIS_HERMES_ENABLED=1`, `IRIS_HERMES_BASE_URL`, `hermes gateway` 실행

## 에디터

| 통합 | 설명 |
|------|------|
| **VS Code** | VS Code Chat에서 Ollama 모델 사용 — [/integrations/vscode](https://docs.ollama.com/integrations/vscode) |

## 기타 통합 (문서 인덱스)

`llms.txt` 기준 추가 항목: Cline, Codex CLI/App, Copilot CLI, Droid, Goose 등.

## Iris Light에서의 선택

| 모드 | 백엔드 | 용도 |
|------|--------|------|
| 단순 채팅 | Ollama only | 대화·thinking |
| 에이전트 | Hermes + Ollama | 파일·터미널·웹·스킬 |

관련: [[00 - Ollama 개요]] · [[02 - API Introduction]] · [[00 - Hermes Agent 개요]]
