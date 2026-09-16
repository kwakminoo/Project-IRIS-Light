# Iris Light 도메인 설계

> 기존 Iris 오케스트레이터를 이식하지 않고, **클라우드·API·오픈소스 에이전트(Ollama + Hermes)** 중심으로 설계한다.  
> Generated-at: 2026-08-25 · Status: 코드 반영 기준으로 갱신 (`0.1.0-light`)

---

## 1. 한 줄 정의

**Iris Light(표시 이름 IRIS)** 는 로컬에 웹검색·셸·파일 IO를 재구현하지 않고,  
사용자가 앱 UI로 요청하면 **Ollama(모델)** + **Hermes Agent(도구·스킬·MCP)** 가 실행하는 **데스크톱 HUD 프레임**이다.

| 구분 | 내용 |
|------|------|
| IRIS가 하는 일 | 세션·권한·스트리밍 UI·시작 프로토콜·Control Surface·워크스페이스 |
| IRIS가 안 하는 일 | 자체 NL→CLI 오케스트레이터, 웹검색/파일IO/셸 재구현 |
| 선택 확장 | Voice STT/TTS, Android 에뮬레이터, Aloha 화면학습 |

---

## 2. 바운디드 컨텍스트 (Bounded Contexts)

```
┌─────────────────────────────────────────────────────────────┐
│                     IRIS App (PyQt6 HUD)                     │
│  Chat · Orb · Wiki · Email · Calendar · IDE · Monitor · …   │
└───────────────┬─────────────────────────────┬───────────────┘
                │ Session / Intent            │ Telemetry
                ▼                             ▼
┌───────────────────────────┐   ┌─────────────────────────────┐
│     Conversation          │   │     Workspace Awareness     │
│  세션·메시지·슬래시·음성턴 │   │  창·메트릭·알림·모니터·콜   │
└─────────────┬─────────────┘   └─────────────────────────────┘
              │
              ▼
┌───────────────────────────┐
│     Runtime Gateway       │  ← 어댑터 (뇌 아님)
│  ollama_client · hermes   │
│  control_surface · setup  │
└───────┬─────────┬─────────┘
        │         │
        ▼         ▼
┌───────────┐ ┌────────────────┐
│  Model    │ │  Agent Runtime │
│  Ollama   │ │  Hermes        │
│ :11434    │ │  :8642 skills  │
└───────────┘ └────────────────┘
```

### 2.1 Presentation
- HUD: Orb, Chat, Live Activity, Sidebar, Monitor, Alerts, Settings
- 워크스페이스(구현): Assistant · Email · Calendar · Iris Wiki · IDE Companion · Mobile(에뮬)
- 준비 중: Instagram / Discord / Kakao / Telegram 아이콘(stub)
- 음성 UI: 마이크·파형·TTS 재생·연속 발화(옵션)

### 2.2 Conversation
- **Session** / **Message** / **Turn** (텍스트 또는 음성 UserTurn)
- 슬래시 커맨드(`/model` 등)는 Hermes로 패스스루
- 음성: STT 결과 → `UserTurnDispatcher`로 채팅 턴 제출(설정에 따라)

### 2.3 Runtime Gateway (핵심)
| 포트/컴포넌트 | 역할 | 기본 |
|---------------|------|------|
| Ollama 클라이언트 | 모델 목록·단순 채팅·헬스 | `:11434` |
| Hermes 클라이언트 | 에이전트 채팅·도구 스트림 | `:8642/v1` |
| Control Surface | Hermes→Iris UI 역제어 HTTP | `:8765` |
| Setup Protocol | 첫 실행 Ollama/Hermes/옵션 설치 | — |
| Voice Runtime | STT/TTS (별도 `.venv-voice`) | `:18765` |

### 2.4 Agent Runtime (외부 — 소유하지 않음)
- Hermes: 파일·터미널·웹·스킬·MCP
- 저장소 동봉 스킬: `integrations/hermes-skills/iris-control/*`
- Hermes 로컬 스킬(iris-apis 등): `%LOCALAPPDATA%\hermes\skills\`
- OpenCode 등 대체 AgentPort는 **미구현 옵션** (문서상 언급만)

### 2.5 Workspace Awareness
- 창/리소스 모니터, 알림 정책, Live Activity
- 전화/알림 낭독(음성 옵션), pinned monitor

### 2.6 Identity & Preferences
- `~/.iris-light/iris_light.db` (SQLite)
- Ollama/Hermes/Voice/Email/Calendar/Control prefs

---

## 3. 핵심 도메인 모델

```text
UserProfile
Settings { ollama_*, hermes_*, voice_prefs_v1, control_* }

ConversationSession { id, created_at, model_ref }
Message { role, content, created_at, tool_traces? }
UserTurn { text, source: chat|voice, barge_in? }

AgentRequest { session_id, text, mode: chat|agent }
AgentEvent  { stream_token | tool_started | tool_finished | done | error }

WorkspaceSnapshot { windows[], metrics, monitor_thumbs[] }
Alert { category, title, message, target_id, policy_decision }
```

### 유스케이스 (현재)

1. **SendMessage** — Chat/Voice → Gateway → Hermes/Ollama → 스트림 UI  
2. **PassSlashCommand** — `/model` 등 Hermes 패스스루  
3. **ShowWorkspace** — Email / Calendar / Wiki / IDE / Mobile  
4. **ManageAlert** — 스누즈/무시 + (옵션) 음성 낭독  
5. **ControlFromHermes** — MCP/HTTP `:8765`로 UI·세션·바이브코딩 제어  
6. **UpdateSettings / Profile** — 로컬 SQLite

---

## 4. 런타임 연결 전략

```
[사용자 자연어 / 음성]
       │
       ▼
[IRIS Chat UI] ──▶ [Hermes :8642]
                       │
          tool calls + iris-control MCP
                       │
          LLM ─────────▶ [Ollama :11434]
                       │
          (필요 시) External APIs / terminal / skills
```

- **기본**: Hermes가 Ollama를 provider로 사용
- **단순 채팅/모델 목록**: Iris → Ollama 직행 가능
- **역제어**: Hermes → Control Surface `:8765` / MCP stdio

| 함 | 안 함 |
|----|------|
| spawn·gateway·스트림 UI·권한 UX | 웹검색·파일IO·셸 자체 구현 |
| Control Surface · iris-control 스킬 | NL→CLI 파인튜닝 |
| 시작 프로토콜·옵션 런타임 설치 | Full Iris 오케스트레이터 이식 |

---

## 5. 코드 구조 (실제)

```
iris/
  ui/                 # Presentation · workspaces · workers · control_bindings
  system/             # setup_protocol, ollama/hermes 기동, control_surface, emulator
  infrastructure/     # ollama_client, hermes_client, email/calendar/…
  runtime/            # UserTurnDispatcher, voice intents
  audio/              # mic, STT/TTS 클라이언트, VAD/AEC, alert speech
  learning/           # Aloha 화면학습
  monitoring/         # monitor · call · notifications
  knowledge/          # Iris Wiki · Obsidian · code_index
  storage/            # SQLite prefs
  mcp/                # iris-control stdio entry
  config / core / assistant / automation / assets
services/
  voice_runtime/      # FastAPI STT/TTS (:18765)
integrations/
  hermes-skills/iris-control/
  hermes-plugins/ · hermes-mcp/ · showui-aloha/
```

---

## 6. 비기능

- **보안**: Hermes 도구는 호스트에 영향 → 확인 다이얼로그·Hermes 설정 따름. Control Surface는 localhost.
- **오프라인**: 로컬 Ollama 모델 시 가능. 클라우드 모델·웹 스킬은 네트워크 필요.
- **데이터**: `~/.iris-light/` — 대화 장기기억은 Hermes memory에 위임 가능.
- **음성**: 기본 prefs는 STT/TTS off. 실사용은 `.venv-voice` + mock 해제.

---

## 7. 기능 상태 (도메인 관점)

| 상태 | 항목 |
|------|------|
| **완료** | HUD · Ollama/Hermes 게이트웨이 · Wiki · Email · Calendar · IDE Companion · Control/MCP · Setup Protocol · Monitor/알림 |
| **선택 완료** | Voice(STT/TTS·프로필·연속발화·콜/알림 낭독) · Android 에뮬 · Aloha 학습 |
| **계획** | 메신저 워크스페이스(Instagram/Discord/Kakao/Telegram) · 데모 YouTube · OpenCode AgentPort |
