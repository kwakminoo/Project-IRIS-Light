# Iris Light 도메인 설계

> 기존 Iris 문서/오케스트레이터를 이식하지 않고, **클라우드·API·오픈소스 에이전트(Ollama + Hermes)** 중심으로 새로 설계한다.
> Generated-at: 2026-07-20

---

## 1. 한 줄 정의

**Iris Light**는 로컬에 도구·모델을 직접 내장하지 않고,  
사용자가 앱 UI(대화)로 요청하면 **Ollama(모델)** + **Hermes Agent(도구·스킬)** 가 실행하는 **데스크톱 프론트엔드**다.

| Full Iris | Iris Light |
|-----------|------------|
| 로컬 STT/TTS, 자체 라우터, 자체 웹검색/컴퓨터유즈 | Ollama API + Hermes(또는 OpenCode) 도구 그대로 사용 |
| 내부에서 명령 파이프라인 구현 | CLI/게이트웨이로 이미 있는 에이전트를 UI로 감쌈 |

---

## 2. 바운디드 컨텍스트 (Bounded Contexts)

```
┌─────────────────────────────────────────────────────────────┐
│                     Iris Light App (UI)                      │
│  Presentation: Orb / Chat / Sidebar / Monitor / Alerts / …   │
└───────────────┬─────────────────────────────┬───────────────┘
                │ Session / Intent            │ Telemetry
                ▼                             ▼
┌───────────────────────────┐   ┌─────────────────────────────┐
│     Conversation          │   │     Workspace Awareness     │
│  대화 세션·메시지·슬래시   │   │  창 목록·메트릭·알림·모니터 │
└─────────────┬─────────────┘   └─────────────────────────────┘
              │
              ▼
┌───────────────────────────┐
│     Runtime Gateway       │  ← Iris가 “명령어를 직접 구현”하지 않음
│  Ollama ↔ Hermes 브리지   │
└───────┬─────────┬─────────┘
        │         │
        ▼         ▼
┌───────────┐ ┌────────────────┐
│  Model    │ │  Agent Runtime │
│  Ollama   │ │  Hermes/OpenCode│
│ (cloud/  │ │  skills/tools  │
│  local)   │ │  이미 내장      │
└───────────┘ └────────────────┘
```

### 2.1 Presentation (이미 이식)
- 메인 HUD: 구체, 채팅, 파형, 러닝 윈도우, 아이콘 그리드, 프로필/설정, 모니터, 알림
- **비포함**: 아이콘 상세 화면, STT/TTS, 자체 오케스트레이터

### 2.2 Conversation
- **Session**: 대화 스레드 ID, 히스토리, `/new`·`/model` 등 슬래시 커맨드 패스스루
- **Message**: user / assistant / tool_trace(표시용)
- **Turn**: 한 번의 사용자 요청 → 에이전트 응답(스트리밍)

### 2.3 Runtime Gateway (핵심 도메인)
Iris Light의 “뇌”가 아니라 **어댑터**.

| 포트 | 역할 |
|------|------|
| `ModelPort` | Ollama OpenAI-compatible `/v1/chat/completions` |
| `AgentPort` | Hermes CLI / Gateway / ACP 중 하나로 NL 요청 전달 |
| `SlashCommandPort` | `/model`, `/skills`, `/stop` 등을 Hermes에 그대로 전달 |

### 2.4 Agent Runtime (외부 시스템 — 소유하지 않음)
- **Hermes**: 파일·터미널·웹·스킬(70+)·메모리 — *이미* tool-calling으로 NL → 도구 실행
- **OpenCode 등**: 코딩 특화 시 동일하게 AgentPort 구현체로 교체 가능
- Iris는 도구를 재구현하지 않고 **세션·권한·UI 피드백**만 담당

### 2.5 Workspace Awareness (로컬 경량)
- Running windows, CPU/GPU/Mem, 창 썸네일 모니터, 알림 정책
- Full Iris의 “능동 에이전트 모니터”와 달리, **표시·알림 UI**가 1차 범위
- 이후 Hermes 이벤트/로그를 알림에 매핑하는 확장 가능

### 2.6 Identity & Preferences
- 사용자 프로필(로컬 SQLite)
- Ollama base URL / model, Hermes 경로·활성화

---

## 3. 핵심 도메인 모델

```text
UserProfile
Settings { ollama_base_url, ollama_model, hermes_* }

ConversationSession { id, created_at, model_ref }
Message { role, content, created_at, tool_traces? }

AgentRequest { session_id, text, mode: chat|agent }
AgentEvent  { stream_token | tool_started | tool_finished | done | error }

WorkspaceSnapshot { windows[], metrics, monitor_thumbs[] }
Alert { category, title, message, target_id, policy_decision }
```

### 유스케이스 (초기)

1. **SendMessage** — UI 텍스트 → Gateway → Hermes/Ollama → 스트림을 ChatPanel에 표시  
2. **PassSlashCommand** — `/model …` 등을 Hermes에 전달 (Iris가 파싱·학습하지 않음)  
3. **ShowWorkspace** — 창 목록·메트릭·모니터 갱신  
4. **ManageAlert** — 스누즈/무시/대상 비활성  
5. **UpdateSettings / Profile** — 로컬 저장

---

## 4. 런타임 연결 전략 (권장)

```
[사용자 자연어]
       │
       ▼
[Iris Chat UI] ──AgentPort──▶ [Hermes]
                                  │
                     tool calls + skills (내장)
                                  │
                     LLM calls ──▶ [Ollama :11434/v1]
                                  │
                     (cloud model도 Ollama가 프록시)
```

- **기본**: Hermes가 Ollama를 provider로 쓰는 구성 (`http://127.0.0.1:11434/v1`)
- **단순 채팅만**: Agent 없이 ModelPort만 (도구 없는 대화)
- **코딩/파일/웹검색**: 반드시 Hermes(또는 OpenCode) AgentPort — Iris가 명령어 매핑 테이블을 두지 않음

### Iris가 추가로 해야 하는 것 / 안 하는 것

| 함 | 안 함 |
|----|------|
| 프로세스 spawn / gateway 연결 | 웹검색·파일IO·셸 자체 구현 |
| 스트림·도구 진행 UI 표시 | NL→CLI 명령어 학습/파인튜닝 |
| 설정·프로필·권한 확인 UX | Full Iris 오케스트레이터 이식 |
| 슬래시 커맨드 패스스루 | 아이콘별 전용 화면(후속) |

---

## 5. 레이어 제안 (코드 구조)

```
iris/
  ui/                 # Presentation (현재 이식됨)
  domain/
    conversation/     # Session, Message, Turn 정책
    workspace/        # Alert, Monitor 규칙 (UI 정책)
    runtime/          # AgentRequest/Event 타입
  application/        # SendMessage, PassSlash 유스케이스
  infrastructure/
    ollama_client/
    hermes_bridge/    # CLI stdin/stdout 또는 gateway API
  config / storage
```

현재 단계는 **ui + config/storage + workspace 표시**까지.  
`application` / `hermes_bridge`는 다음 스프린트.

---

## 6. 비기능

- **보안**: Hermes 도구는 호스트에 영향 → 확인 다이얼로그·샌드박스(Docker)는 Hermes 설정을 따름
- **오프라인**: Ollama 로컬 모델 시 가능, 클라우드 모델·웹 스킬은 네트워크 필요
- **데이터**: 프로필·알림 prefs는 `~/.iris-light/` — 대화 장기기억은 Hermes memory에 위임 가능

---

## 7. 로드맵 (도메인 관점)

1. ~~메인 HUD UI 셸~~ (이번)
2. Ollama ModelPort 연결 (채팅 에코 제거)
3. Hermes AgentPort (NL 에이전트 턴)
4. 슬래시 커맨드·툴 트레이스 UI
5. 아이콘 상세 화면 / 메시징 게이트웨이(선택)
