# Hermes Agent 개요

> Source: https://hermes-agent.nousresearch.com/docs  
> 정리일: 2026-07-20  
> 제작: Nous Research

## 한 줄 정의

**Hermes Agent**는 Nous Research가 만든 **자기 개선(self-improving) AI 에이전트**입니다.  
스킬 생성·개선, 세션 간 메모리, 70+ 내장 스킬, 20+ 메시징 플랫폼 Gateway, MCP 연동을 제공합니다.

Iris Light에서는 Hermes를 **AgentPort**(도구·스킬 실행 백엔드)로 사용합니다.

## Iris Light와의 관계

```
[Iris Light UI] ──Hermes API──▶ [Hermes Agent]
                                    ├─ 도구 (terminal, web, browser, …)
                                    ├─ 스킬 (70+ bundled)
                                    ├─ MCP 서버 도구
                                    └─ LLM ──▶ Ollama / OpenRouter / …
```

| Iris Light | Hermes |
|------------|--------|
| HUD·채팅·워크스페이스 UI | NL → 도구 실행 |
| `HermesChatWorker` | gateway API `/v1/chat/completions` |
| 설정 `IRIS_HERMES_*` | `~/.hermes/config.yaml` |

관련: [[05 - API Server와 Iris Light 연동]]

## 설치 (요약)

### Windows (PowerShell)

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

### Linux / macOS / WSL2

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

### Ollama 경유 빠른 시작

```bash
ollama launch hermes
```

자세히: [[01 - 설치와 설정]]

## 핵심 특징

| 영역 | 내용 |
|------|------|
| **학습 루프** | 메모리 큐레이션, 스킬 자동 생성·개선, Honcho 사용자 모델링 |
| **실행 환경** | local, Docker, SSH, Daytona, Singularity, Modal (6 backends) |
| **메시징** | Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Matrix 등 20+ |
| **도구** | 웹검색, 터미널, 파일, 브라우저, 비전, TTS, 이미지 생성, cron |
| **MCP** | stdio/HTTP MCP 서버 연결, 도구 자동 등록·필터링 |
| **스킬** | agentskills.io 호환, ~90 bundled + ~60 optional |
| **API** | OpenAI 호환 HTTP (`/v1/chat/completions`) |
| **자동화** | cron, subagent delegation, hooks, batch processing |

## 문서 구조 (이 Vault)

- [[01 - 설치와 설정]]
- [[02 - 핵심 기능 (도구·메모리·스킬)]]
- [[03 - MCP 연동]]
- [[04 - 자동화와 Gateway]]
- [[05 - API Server와 Iris Light 연동]]
- [[06 - 이메일과 생산성 스킬]]
- [[07 - Skills 카탈로그 요약]]

## 공식 링크

| 항목 | URL |
|------|-----|
| 문서 홈 | https://hermes-agent.nousresearch.com/docs |
| GitHub | https://github.com/NousResearch/hermes-agent |
| Ollama 연동 | https://docs.ollama.com/integrations/hermes |
| LLM용 인덱스 | https://hermes-agent.nousresearch.com/docs/llms.txt |

## 추천 모델 (Ollama)

**클라우드:** `kimi-k2.5:cloud`, `glm-5.1:cloud`, `qwen3.5:cloud`, `minimax-m2.7:cloud`  
**로컬:** `gemma4`, `qwen3.6`
