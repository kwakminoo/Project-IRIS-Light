# Iris Light — Information Architecture (IA)

> Generated-at: 2026-08-25  
> 관련 이미지: [iris-system-architecture.png](./iris-system-architecture.png) · [iris-light-ia.png](./iris-light-ia.png)

## 1. 한 줄 정의

**Iris Light는 Ollama(모델)와 Hermes Agent(도구·스킬)를 감싸는 데스크톱 HUD 프레임(프론트엔드)** 이다.  
웹검색·터미널·스킬 실행은 Iris가 직접 구현하지 않고 Hermes 게이트웨이에 위임한다.

| 질문 | 답 |
|------|-----|
| Iris가 “뇌”인가? | 아니오 — **어댑터/프레임** |
| 모델은? | **Ollama** (`:11434`, 로컬/클라우드) |
| 도구·스킬은? | **Hermes** (`:8642` API Server) |
| Iris 역제어? | **Control Surface** (`:8765`) + iris-control MCP |
| 음성(선택)? | **Voice Runtime** (`:18765`) |
| 외부 SERP/크롤? | Hermes 플러그인·스킬 → SerpApi / Exa / Firecrawl 등 |

## 2. 시스템 구성 및 아키텍처

![IRIS 시스템 구성 및 아키텍처](./iris-system-architecture.png)

개조식 요약:

- **시스템 구성**: 사용자 → IRIS HUD(PyQt6) → Runtime Gateway → Ollama(:11434) / Hermes(:8642) → SQLite · Voice Runtime · Control Surface · External APIs
- **기술 스택·역할**: Presentation(UI) · Runtime(세션·UserTurn) · Infrastructure(어댑터) · Model(Ollama) · Agent(Hermes) · Storage(SQLite) · Optional(Voice/Android/Aloha)
- **핵심 데이터 흐름**: Chat/Voice Send → Hermes completions → Ollama 추론 → tools/skills → 스트림 UI (단순 채팅은 ModelPort 직행)

## 3. IA 다이어그램

![Iris Light IA](./iris-light-ia.png)

```mermaid
flowchart TB
  subgraph IRIS["Iris Light — PyQt6 HUD 프레임"]
    UI["Presentation<br/>Chat · Orb · Wiki · Email · Calendar · IDE · Monitor"]
    GW["Runtime Gateway<br/>hermes_client · ollama_client"]
    CS["Control Surface :8765"]
    DB["Local Store<br/>~/.iris-light/*.db"]
    UI --> GW
    UI --> DB
    CS --> UI
  end

  subgraph MODEL["Model Runtime"]
    OLL["Ollama :11434<br/>/v1/chat/completions · /api/show"]
  end

  subgraph AGENT["Agent Runtime"]
    HER["Hermes Gateway :8642<br/>/v1/chat/completions · tools · skills"]
    SK["Skills iris-control/*<br/>(+ Hermes local iris-apis/*)"]
    WP["Web providers<br/>serpapi · firecrawl · exa"]
    HER --> SK
    HER --> WP
  end

  subgraph VOICE["Voice (optional)"]
    VR["Voice Runtime :18765<br/>STT / TTS"]
  end

  subgraph EXT["External APIs"]
    SERP["SerpApi"]
    FC["Firecrawl"]
    EXA["Exa"]
    NV["Naver Open API"]
  end

  GW -->|"채팅·도구"| HER
  HER -->|"추론"| OLL
  HER -->|"역제어 MCP/HTTP"| CS
  UI -->|"음성"| VR
  WP --> SERP
  WP --> FC
  WP --> EXA
  SK --> NV
```

## 4. 레이어 설명

| 레이어 | 책임 | 소유 |
|--------|------|------|
| **Presentation** | HUD, 채팅 스트림, 워크스페이스, 모니터 | Iris |
| **Runtime Gateway** | Hermes/Ollama HTTP 어댑터, Setup Protocol | Iris |
| **Control Surface** | Hermes→UI 역제어 (`:8765`) | Iris |
| **Model Runtime** | LLM 추론 | Ollama (외부) |
| **Agent Runtime** | tool-calling, 스킬, 웹 백엔드 | Hermes (외부) |
| **Voice Runtime** | STT/TTS (옵션) | Iris `services/voice_runtime` |
| **External APIs** | SERP/크롤/검색 키 | Hermes `.env` |

## 5. 사용자 요청 경로 (스타트 → 엔드)

1. 사용자 → Iris Chat Send (또는 음성 UserTurn)  
2. Iris → `POST http://127.0.0.1:8642/v1/chat/completions` (Hermes)  
3. Hermes → Ollama로 추론 (tools 지원 모델)  
4. 필요 시 Hermes → `web_search` / 스킬 / terminal / iris-control  
5. 스트림 → Iris Live Activity + 채팅 UI (+ 옵션 TTS)

## 6. 설정 파일 IA

| 파일 | 내용 |
|------|------|
| 프로젝트 `.env` | `IRIS_OLLAMA_*`, `IRIS_HERMES_*`, (선택) `IRIS_CONTROL_*`, `IRIS_DATA_GO_KR_*`, `IRIS_SETUP_*` |
| `%LOCALAPPDATA%\hermes\.env` | `SERPAPI_API_KEY`, Exa, Firecrawl, Naver, `API_SERVER_KEY`… |
| `%LOCALAPPDATA%\hermes\config.yaml` | `web.search_backend`, `model.provider` 등 |
| `integrations/hermes-skills/iris-control/` | Iris 역제어 스킬(재배포용) |
| `integrations/hermes-plugins/web/serpapi/` | SerpApi 플러그인 소스 |

## 7. 관련 문서

- [../domain.md](../domain.md) — 도메인·바운디드 컨텍스트  
- [../api/API-명세서.md](../api/API-명세서.md) — API 엔드포인트 명세  
- [../voice.md](../voice.md) · [../voice_architecture.md](../voice_architecture.md) — 음성  
- Wiki: [[프로젝트 개요]] · [[API 명세서]]
