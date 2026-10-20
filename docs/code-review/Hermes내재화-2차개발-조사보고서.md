# Hermes 런타임 내재화 — 2차 개발 조사 보고서

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-20-HERMES-ABSORB |
| 작성일 | 2026-10-20 |
| 관련 | 1차 Iris Light 완성 후 에이전트 백엔드 재편, 연구·2차 개발 선행 조사 |
| 대상 | Iris Light ↔ Hermes Agent 현재 구조, 업스트림 능력, 내재화 전략 |
| 목적 | “Hermes를 Iris 안에 녹인다”는 목표의 뜻을 고정하고, 진행 순서를 제안한다 |

## 1. 결론

지금은 Iris가 Hermes를 **별도 OS 프로세스·별도 홈**으로 두고, HTTP(`:8642`)로 채팅하고 MCP로 UI를 역제어하는 **AgentPort 연동**이다. 제품 문장으로 “합친다”고 쓰면 엔지니어링과 어긋난다. 맞는 표현은 **Iris-on-Hermes**, 즉 Iris 제품 껍질이 Hermes 에이전트 런타임을 **소유·확장**하는 것이다.

권고는 **한 프로세스에 코드를 밀어 넣는 big-bang이 아니다.** 먼저 Iris가 소유한 Hermes 포크(또는 고정 벤더)로 soft-patch·설치·업데이트를 흡수하고, 프로세스 경계와 Control Surface는 유지한다. UI·위키·메일·IDE·스케줄은 Iris에 남긴다. 도구 루프·스킬·메모리·MCP 호스팅은 Hermes 쪽에 둔다. MIT(Hermes)는 Iris GPL과 양립 가능하나, 소스를 저장소에 넣으면 `LICENSE.md` §3.4의 “번들하지 않음” 전제를 고쳐야 한다.

근거는 레포 코드, `%LOCALAPPDATA%\hermes` 설치본, `obsidian-vault/Hermes/`, GitHub `NousResearch/hermes-agent`(MIT)다.

## 2. 용어

| 표현 | 판단 |
|---|---|
| “Hermes를 Iris에 합친다” | 모호. 프로세스·라이선스·제품 경계가 한 문장에 안 담긴다. |
| “Iris가 Hermes를 플러그인으로 둔다” | **현재 상태**에 가깝다. 2차 목표와 반대다. |
| “Iris-on-Hermes / Hermes 런타임 내재화” | 권고. Iris=제품·HUD·도메인 액션, Hermes=에이전트 엔진(도구·스킬·메모리). |
| “in-process embed” | 별도 옵션. Qt와 agent loop를 한 프로세스에 넣는 것. 지금은 비권고. |

## 3. 구조

요청이 디스크·게이트웨이·도구·화면까지 가는 경로.

```
[사용자 Iris 채팅]
    → MainWindow / HermesChatWorker          (iris/ui/…)
    → HermesClient.stream_chat               (iris/infrastructure/hermes_client.py)
    → HTTP 127.0.0.1:8642 /v1/chat/completions
    → [Hermes gateway 프로세스]              (%LOCALAPPDATA%\hermes\hermes-agent)
         ├─ SOUL.md / MEMORY.md / skills
         ├─ built-in tools + MCP tools
         ├─ LLM → Ollama :11434 또는 custom API
         └─ MCP iris-control (stdio, pythonw)
              → iris/mcp/iris_control_stdio.py
              → HTTP Control Surface :8765   (iris/system/control_surface.py)
              → email.* / wiki.* / project.run / chat.exec_python / emulator.* …

[Iris 기동]
    HermesHealthWorker
      → sync_iris_control (config·skills·SOUL·MEMORY·terminal off·패치)
      → ensure_hermes_gateway_running
```

이번 조사에서 갈라지는 지점.

| 분기 | 위치 | 의미 |
|---|---|---|
| 채팅 백엔드 | `hermes_enabled` (기본·강제 ON) | 도구 호출은 Hermes 경유. 끄기 거부. |
| 설치본 vs 홈 | `hermes-agent/` vs `%LOCALAPPDATA%\hermes\` | 코드와 런타임 상태 분리. |
| Iris→Hermes | `hermes_iris_control_sync` 등 | 디스크에 정책·MCP·페르소나 주입. |
| Hermes→Iris | iris-control MCP | Iris가 떠 있을 때만 UI 조작. |
| Iris 단독 루프 | `chat_code_exec`, `routine_runner`, Control Surface | Hermes agent loop의 복제가 아님. |

```
현재 (연동)
  Iris 제품 ──HTTP──▶ Hermes(외부 설치) ──MCP──▶ Iris Control

목표 (내재화, 권고 1단계)
  Iris 제품 ──HTTP──▶ Hermes(Iris 소유 포크·고정 버전) ──MCP/내장 브리지──▶ Iris Control

비권고(당장)
  Iris 프로세스 안에 Hermes agent loop import
```

## 4. 코드 리뷰

경로상 지점이 이번 목표에서 한 일과, “녹여내기”를 막거나 왜곡하는 이유.

| 지점 | 파일 | 한 일 | 한계 |
|---|---|---|---|
| 설치 | `iris/system/hermes_install.py` | Windows에서 공식 install.ps1 우회, clone·venv | 여전히 **외부 트리**. soft-fork. |
| 홈·키 | `hermes_credentials.py` | `hermes_home()` → `%LOCALAPPDATA%\hermes`, `API_SERVER_KEY` | Iris `~/.iris-light`와 **이중 홈**. |
| 게이트웨이 | `hermes_gateway.py` | spawn/stop/진단, Iris venv 격리 | 자식 프로세스 전제. in-process와 충돌. |
| 클라이언트 | `hermes_client.py` | `/health`, `/v1/models`, SSE 채팅, 모델 동기화 | OpenAI 호환 **경계 API**. 내부 루프에 손 안 댐. |
| 워커 | `hermes_workers.py` | sync → gateway → `stream_chat` | UI와 엔진을 붙이는 접착제. |
| 동기화 | `hermes_iris_control_sync.py` | MCP·스킬·terminal off·stdio 패치 | Hermes 디스크를 Iris가 씀. **업데이트에 패치 덮임**. |
| 페르소나 | `hermes_soul_sync.py`, `integrations/hermes-soul/SOUL.md` | “너는 Hermes가 아니다. 아이리스다.” | 엔진은 Hermes, **정체성은 Iris**. |
| 메모리 정책 | `hermes_memory_nudge.py` | `MEMORY.md`에 iris-control 계약 | 긴 정책이 스킬보다 두꺼움. |
| 제어면 | `control_surface.py`, `iris/mcp/*` | Hermes→Iris 도구 실행 | 합쳐도 **분리 유지가 맞음**. |
| 라우팅 | `backend_route.py`, `model_failover.py` | 어느 백엔드로 보낼지 | Hermes 내부 retry와 이중 체인. |
| 라이선스 | `LICENSE.md` §3.4 | Hermes를 “번들 안 함·별도 프로세스”로 기술 | **소스 내재화 시 이 절 개정 필수**. |

하지 않은 일 (이번 요청 범위 밖·현행 유지).

- Hermes messaging Gateway(Telegram 등)를 Iris UI에 이식하지 않음.
- `/v1/responses` 서버측 대화 상태를 Iris 기본 경로로 쓰지 않음 (vault·코드상 Completions+클라이언트 history).
- SerpApi Hermes 플러그인 자동 sync 없음 (수동 복사).
- in-process agent loop 설계·프로토타입 없음.

확인한 사실.

| 사실 | 출처 |
|---|---|
| Windows 홈 = `%LOCALAPPDATA%\hermes`, 소스 = `...\hermes\hermes-agent` | 이 PC 설치본 목록, `hermes_credentials` |
| API `:8642`, Control `:8765` | vault 05, `control_surface`, `hermes_gateway` |
| `agent.disabled_toolsets: [terminal]` | 현장 `config.yaml` |
| 업스트림 라이선스 MIT | GitHub API, `pyproject.toml` `license = "MIT"` |
| Iris는 Hermes를 필수 AgentPort로 취급 | settings에서 `hermes_enabled` 끄기 거부 |

## 5. Hermes 업스트림 능력 (흡수 후보 지도)

Nous Research `hermes-agent`. 문서 정리: `obsidian-vault/Hermes/`.

| 영역 | 내용 | Iris와의 관계 |
|---|---|---|
| Tools | 60+ , toolset 단위. web, terminal/file, browser, vision/TTS/image, todo/delegate/execute_code, memory, cron, HA/MCP | Iris는 terminal을 끄고 Control로 우회 |
| 실행 백엔드 | local, docker, ssh, singularity, modal, daytona | Iris IDE/`project.run`과 역할 겹침 가능. 정책 필요 |
| Memory | MEMORY.md, USER.md, session_search(FTS5), 외부 provider 8종 | Iris DB와 이중 기억. 내재화 시 소유권 결정 필요 |
| Skills | ~90 bundled + ~60 optional, `/learn`, Hub | Iris는 `iris-control/*` 10개만 주입 |
| Gateway | 메시징 20+ + 동일 프로세스 API Server | Iris는 API Server만 사용 |
| MCP | stdio/HTTP/OAuth, catalog | Iris는 MCP 호스트가 아님. Hermes에 위임 |
| API | `/v1/chat/completions`, `/v1/responses`, SSE `hermes.tool.progress` | Iris 채팅의 실계약 |
| Providers | Ollama, OpenRouter, OpenAI, Nous Portal, custom | Iris 모델 피커와 sync |

Iris가 이미 넣은 확장 (`integrations/`).

- Skills: work-start/end, session-status, vibe-code, emulator, mobile-mcp, learning, calendar, wiki, email
- MCP entry: `iris_control_stdio_entry.py`
- Soul: Iris 페르소나
- Plugin: SerpApi (수동)

## 6. 개선안 (구조의 빈자리만)

| 빈자리 | 내용 |
|---|---|
| A. 소유권 | Hermes가 “외부 앱”이 아니라 Iris 릴리스가 pin한 엔진이어야 한다. |
| B. soft-fork 해소 | `ollama_options_guard`, `mcp_tool` dead-check 등 설치본 패치를 포크 또는 업스트림 PR로 고정. |
| C. 이중 홈 | `%LOCALAPPDATA%\hermes` vs `~/.iris-light`를 제품 관점에서 한 이름으로 정리(심볼릭/별칭 가능). |
| D. 역제어 비용 | sync→디스크→gateway restart→MCP→HTTP 왕복. 내재화 후에도 Control Surface HTTP는 유지하되, 배포·entry를 Iris 패키지 안으로. |
| E. 라이선스 문서 | 소스 포함 시 §3.4 개정 + MIT 고지 유지. |
| F. 제품 언어 | UI/문서에서 Hermes 브랜드를 점진적으로 Iris Agent로. 엔진 커밋·어트리뷰션은 유지. |

당장 메우지 말 것.

- Qt 메인 프로세스에 agent loop import
- Hermes messaging Gateway를 Iris에 이식
- MEMORY를 하루아침에 Iris SQLite로만 이전 (Hermes identity slot과 충돌)

## 7. 진행 방안 (권고)

### 7.1 대안 비교

| 방안 | 요약 | 장점 | 단점 | 판단 |
|---|---|---|---|---|
| 0. 현상 유지 | 외부 Hermes + Iris sync/patch | 빠름, LICENSE §3.4 유지 | soft-fork·이중 홈·“외부 앱” 느낌 | 2차 목표와 불일치 |
| 1. Iris 소유 포크 + 프로세스 유지 | 포크/벤더 pin, spawn은 그대로 | 패치 고정, 제품 소유, 위험 낮음 | 업데이트 짐, 어트리뷰션 | **권고** |
| 2. 모노레포 벤더 + 자식 프로세스 | `vendor/hermes-agent` 등 | 리뷰 가시성 | 레포 비대, Python 버전 충돌 | 1의 변형으로 가능 |
| 3. in-process 라이브러리화 | import agent loop | 프로세스 하나 | Qt·콘솔·크래시·디버그 폭발 | 연구 단계 후순위 |
| 4. 엔진 재작성 | Hermes 없이 Iris에 루프 재구현 | 완전 소유 | 스킬·MCP·메모리 재발명 | YAGNI. 비권고 |

### 7.2 단계

| 단계 | 결과 | 완료 기준 |
|---|---|---|
| 1. 계약 고정 | 문서·이슈에 Iris-on-Hermes 정의, 프로세스 유지 명시 | 팀이 같은 문장으로 목표를 말함 |
| 2. 소유 포크 | Iris가 pin한 Hermes 트리(포크 또는 vendor). 설치가 그 트리만 씀 | `hermes_install`이 upstream main 대신 pin SHA |
| 3. 패치 흡수 | ollama options·stdio dead-check·terminal policy를 포크에 커밋 | `hermes update` 후 패치 재적용 불필요 |
| 4. 배포 일체화 | Iris 설치/업데이트 UX가 엔진 버전을 함께 올림 | 사용자에게 “Hermes 따로 설치” 최소 |
| 5. 홈 정리 | `IRIS_AGENT_HOME` 등으로 제품 통일(하위 호환 alias) | sync·gateway·client가 한 루트 |
| 6. 브랜드 | UI 칩·문구를 Iris Agent로. LICENSE·NOTICE에 Nous MIT | 사용자는 Iris로 인식, 고지는 남음 |
| 7. (연구) in-process | 프로토타입·크래시·콘솔 창 계약 검증 후에만 | prove 스크립트 통과 시에만 채택 검토 |

### 7.3 손대지 말 경계

- `control_surface` / Qt UI / wiki·email·IDE companion
- Ollama 별도 프로세스
- `chat_code_exec` 화이트리스트와 Hermes sandbox의 역할 구분

## 8. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않는 이유 |
|---|---|---|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT) | agent loop, tools, skills, memory, MCP host, API server | 이미 AgentPort. 내재화는 **소유·배포** 문제이지 기능 재작성 문제가 아님 |
| agentskills.io / Skills Hub | 스킬 형식·progressive disclosure | Iris 스킬은 이미 호환 형식으로 주입 중 |
| OpenAI Chat Completions + Responses | Iris↔엔진 경계 API | 지금 Completions만. Responses는 세션 서버화 때 |
| MCP (stdio) | 외부 도구·역제어 | Control Surface를 MCP 없이 직접 붙이는 건 가능하나, 생태계·Hermes 관례상 당분간 유지 |
| Cursor / CCR식 model failover | Iris `model_failover` | Hermes 내부 retry와 합치기 전 역할 분리 유지 |
| 찾지 못함 | “데스크톱 HUD + 풀 에이전트 엔진”을 한 저장소에 합친 동일 제품 레퍼런스 | Open WebUI 등은 채팅 UI+백엔드이지 Iris식 Control Surface 역제어와 다름 |

## 9. 조치

1. 2차 개발 킥오프 전에 목표 문장을 **Iris-on-Hermes (프로세스 유지, 포크 소유)** 로 고정한다.
2. 다음 구현 작업(별도 Feature)에서 Hermes pin 포크와 `hermes_install` 진입을 연결한다.
3. soft-patch 목록을 포크 이슈로 옮기고, 업스트림 PR 가능 항목은 분리한다.
4. 소스 번들 결정 시 `LICENSE.md` §3.4와 NOTICE를 같은 PR에서 고친다.
5. in-process embed는 연구 백로그에만 두고, 1~6단계 증거 없이 착수하지 않는다.

---

## 부록 A. Overview (how)

Iris Light는 데스크톱 HUD·워크스페이스·Control Surface를 소유한다. Hermes는 도구·스킬·메모리·MCP를 돌리는 에이전트 런타임이다. 채팅은 OpenAI 호환 HTTP다. UI 조작은 Hermes가 MCP로 Iris에 돌아온다.

## 부록 B. Key concepts

- AgentPort: Iris가 말하는 “에이전트 백엔드” = Hermes gateway API
- soft-fork: 의존성이지만 설치본을 패치하는 상태
- 이중 홈: Hermes home vs Iris light home
- 역제어: Hermes→Iris Control Surface

## 부록 C. Where things live

| 위치 | 내용 |
|---|---|
| `iris/system/hermes_*.py` | 설치·gateway·sync·update |
| `iris/infrastructure/hermes_*.py` | HTTP·자격 |
| `iris/ui/workers/hermes_workers.py` | Qt 워커 |
| `integrations/hermes-*` | skills, mcp entry, soul, plugins |
| `%LOCALAPPDATA%\hermes\` | Windows 런타임·소스 |
| `obsidian-vault/Hermes/` | 업스트림 기능 요약 |

## 부록 D. Gotchas

- `/health` OK ≠ 채팅 가능 (Bearer/`API_SERVER_KEY`)
- Gateway 자식에서 Iris `.venv`를 벗기지 않으면 trampoline 실패
- MCP entry에 frozen `IRIS.exe`/`_MEI` 금지
- `hermes update`가 Iris 패치를 지움
- Hermes ON이면 설정 smoke와 실채팅 경로가 다를 수 있음 (과거 400/401 문서)
