# Iris Light 도메인 설계

> Iris Light의 에이전트 코어는 Hermes를 감싸지 않고 **흡수한 Iris Agent**다.  
> 모델은 Ollama, 도구·스킬·루프는 Iris Agent 런타임이 맡는다.  
> Generated-at: 2026-10-28 · Status: §10.1 일체화 반영 (`0.1.0-light`)

---

## 1. 한 줄 정의

**Iris Light(표시 이름 IRIS)** 는 로컬에 웹검색·셸·파일 IO를 재구현하지 않고,  
사용자가 앱 UI로 요청하면 **Ollama(모델)** + **Iris Agent(도구·스킬·MCP 호스트)** 가 실행하는 **데스크톱 HUD**다.

| 구분 | 내용 |
|------|------|
| IRIS가 하는 일 | 세션·권한·스트리밍 UI·시작 프로토콜·Control Surface·워크스페이스·Iris Agent 수명 |
| IRIS가 안 하는 일 | 자체 NL→CLI 오케스트레이터, 웹검색/파일IO/셸을 UI 프로세스 안에 다시 짜기 |
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
│     Runtime Gateway       │  ← 어댑터 + Iris Agent supervisor
│  ollama_client · engine   │
│  control_surface · setup  │
└───────┬─────────┬─────────┘
        │         │
        ▼         ▼
┌───────────┐ ┌────────────────────────────┐
│  Model    │ │  Iris Agent Runtime        │
│  Ollama   │ │  홈 ~/.iris-light/agent    │
│ :11434    │ │  기본 InternalSidecar      │
└───────────┘ │  (옵션 ExternalGateway)    │
              └────────────────────────────┘
```

### 2.1 Presentation
- HUD: Orb, Chat, Live Activity, Sidebar, Monitor, Alerts, Settings
- 워크스페이스(구현): Assistant · Email · Calendar · Iris Wiki · IDE Companion · Mobile(에뮬)
- 준비 중: Instagram / Discord / Kakao / Telegram 아이콘(stub)
- 음성 UI: 마이크·파형·TTS 재생·연속 발화(옵션)

### 2.2 Conversation
- **Session** / **Message** / **Turn** (텍스트 또는 음성 UserTurn)
- 슬래시 커맨드(`/model` 등)는 Iris Agent 턴으로 패스스루
- 음성: STT 결과 → `UserTurnDispatcher`로 채팅 턴 제출(설정에 따라)

### 2.3 Runtime Gateway (핵심)
| 포트/컴포넌트 | 역할 | 기본 |
|---------------|------|------|
| Ollama 클라이언트 | 모델 목록·단순 채팅·헬스 | `:11434` |
| Iris Agent 엔진 | 말 턴·도구 스트림 (`iris/engine`, 워커) | InternalSidecar |
| ExternalGateway (옵션) | 레거시 HTTP 게이트웨이 | `:8642/v1` |
| Control Surface | 에이전트→Iris UI 역제어 HTTP | `:8765` (비시드 compat) |
| Setup / supervisor | 첫 실행·핀·에이전트 수명 | `ensure_iris_agent_runtime` |
| Voice Runtime | STT/TTS (별도 `.venv-voice`) | `:18765` |

### 2.4 Iris Agent Runtime (제품 소유)
- 홈: `IRIS_AGENT_HOME` 또는 `~/.iris-light/agent` (Windows는 `%USERPROFILE%\.iris-light\agent`)
- 기본 말 턴: **InternalSidecar** (`shared_engine`)
- 도구: 제품 경로 seed는 native `IrisAgentToolRegistry`. 비시드 Control 액션은 `:8765` MCP compat
- 저장소 동봉 스킬: `integrations/hermes-skills/iris-control/*` (동기화 대상은 제품 에이전트 홈)
- 업스트림 크레딧: NOTICE의 Nous Hermes Agent (MIT)

### 2.5 Workspace Awareness
- 창/리소스 모니터, 알림 정책, Live Activity
- 전화/알림 낭독(음성 옵션), pinned monitor

### 2.6 Identity & Preferences
- `~/.iris-light/iris_light.db` (SQLite) — 채팅 정본
- Ollama / Iris Agent / Voice / Email / Calendar / Control prefs

---

## 3. 핵심 도메인 모델

```text
UserProfile
Settings { ollama_*, hermes_enabled(필수 게이트), voice_prefs_v1, control_* }

ConversationSession { id, created_at, model_ref }
Message { role, content, created_at, tool_traces? }
UserTurn { text, source: chat|voice, barge_in? }

AgentRequest { session_id, text, mode: chat|agent }
AgentEvent  { stream_token | tool_started | tool_finished | done | error }

WorkspaceSnapshot { windows[], metrics, monitor_thumbs[] }
Alert { category, title, message, target_id, policy_decision }
```

### 유스케이스 (현재)

1. **SendMessage** — Chat/Voice → Iris Agent 엔진 → (추론은 Ollama) → 스트림 UI  
2. **PassSlashCommand** — `/model` 등 에이전트 턴 패스스루  
3. **ShowWorkspace** — Email / Calendar / Wiki / IDE / Mobile  
4. **ManageAlert** — 스누즈/무시 + (옵션) 음성 낭독  
5. **ControlFromAgent** — MCP/HTTP `:8765`로 UI·세션·바이브코딩 제어 (compat)  
6. **UpdateSettings / Profile** — 로컬 SQLite

---

## 4. 런타임 연결 전략

```
[사용자 자연어 / 음성]
       │
       ▼
   [IRIS Chat UI]
       │
       ▼
   [Iris Agent — InternalSidecar 기본]
       │
       ├─ LLM ─────────▶ [Ollama :11434]
       ├─ native tools ▶ IrisAgentToolRegistry (seed)
       └─ (옵션) ExternalGateway :8642
                      │
         (비시드 compat) Control :8765 / MCP
```

- **기본**: Iris Agent InternalSidecar가 Ollama를 provider로 사용
- **단순 채팅/모델 목록**: Iris → Ollama 직행 가능
- **역제어**: 비시드 액션만 Control Surface `:8765` / MCP stdio (compat)

| 함 | 안 함 |
|----|------|
| spawn·엔진·스트림 UI·권한 UX | 웹검색·파일IO·셸을 UI에 자체 재구현 |
| Control Surface · iris-control 스킬 | NL→CLI 파인튜닝 |
| 시작 프로토콜·핀된 Iris Agent 설치 | Full Iris 구 오케스트레이터 이식 |
| 구 `%LOCALAPPDATA%\hermes`를 활성 홈으로 쓰기 (활성 홈 아님) | (마이그레이션 잔여만 허용) |

---

## 5. 코드 구조 (실제)

```
iris/
  ui/                 # Presentation · workspaces · workers · control_bindings
  engine/             # Iris Agent InternalSidecar / ExternalGateway
  system/             # setup_protocol, agent gateway, control_surface, emulator
  infrastructure/     # ollama_client, hermes_client(어댑터명), agent_tool_registry
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
  hermes-skills/iris-control/   # 스킬 소스 (제품명 Iris Agent)
  hermes-plugins/ · hermes-mcp/ · showui-aloha/
vendor/
  iris-agent-runtime/ # pin SHA
```

패턴·증상별 수정 위치·UI 커스텀: [`guides/extending-iris.md`](guides/extending-iris.md).  
패키지 경계(pydoc): 각 `iris/**/__init__.py` 의 `Agent-readable`.

---

## 6. 비기능

- **보안**: Iris Agent 도구는 호스트에 영향 → 확인 다이얼로그·에이전트 정책. Control Surface는 localhost.
- **오프라인**: 로컬 Ollama 모델 시 가능. 클라우드 모델·웹 스킬은 네트워크 필요.
- **데이터**: `~/.iris-light/` — 대화 정본은 Iris SQLite. 에이전트 메모리는 제품 홈 아래.
- **음성**: 기본 prefs는 STT/TTS off. 실사용은 `.venv-voice` + mock 해제.

---

## 7. 기능 상태 (도메인 관점)

| 상태 | 항목 |
|------|------|
| **완료** | HUD · Iris Agent(§10.1) · Wiki · Email · Calendar · IDE Companion · Control/MCP · Setup · Monitor/알림 |
| **선택 완료** | Voice(STT/TTS·프로필·연속발화·콜/알림 낭독) · Android 에뮬 · Aloha 학습 |
| **계획** | 메신저 워크스페이스 · 데모 YouTube · Phase 5 in-process Merge(선택) |
