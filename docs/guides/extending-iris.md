# Extending IRIS — 코어 불변 · 확장점

| 항목 | 내용 |
|------|------|
| 목적 | 외부 기여자가 **코어 diff=0**으로 기능을 추가하는 절차 |
| 작성일 | 2026-09-23 |
| 갱신 | 2026-10-28 — Iris Agent 일체화(홈·InternalSidecar) 반영 |
| 관련 | `docs/domain.md` · `integrations/hermes-skills/README.md` · `CONTRIBUTING.md` |

---

## 1. 한 장 다이어그램

```text
┌──────────────────────────────────────────────────────────┐
│ CORE (가급적 불변)                                        │
│  iris/runtime/   UserTurnDispatcher                       │
│  iris/engine/    InternalSidecar · ExternalGateway        │
│  iris/system/    setup_protocol · agent supervisor · CS   │
│  iris/infrastructure/  ollama_client · hermes_client      │
│  iris/core/ · iris/storage/                               │
└───────────────┬──────────────────────────┬───────────────┘
                │ HTTP / MCP / native        │ 스킬 동기화
                ▼                            ▼
┌───────────────────────────┐  ┌─────────────────────────────┐
│ EXTENSION                 │  │ EXTENSION                   │
│  integrations/hermes-     │  │  iris/mcp/                  │
│    skills/iris-control/*  │  │  integrations/iris-ide/     │
│  integrations/archify/    │  │  integrations/showui-aloha/ │
│  services/voice_runtime/  │  │  (별도 프로세스 권장)         │
└───────────────────────────┘  └─────────────────────────────┘
```

| 레이어 | 역할 | 기여자 기본 태도 |
|--------|------|------------------|
| Core | 세션·Gateway·Iris Agent 수명·권한 경계 | **수정 최소화** — 버그/보안만 |
| Extension | 스킬 · MCP · IDE · Aloha · Voice | **여기부터 추가** |

---

## 2. 새 Iris Agent 스킬 추가 (코어 diff=0)

목표: `iris/runtime` · `iris/system` · `iris/infrastructure`에 **파일 변경 0**.

1. `integrations/hermes-skills/iris-control/iris-<name>/SKILL.md` 작성  
   - 기존 `iris-wiki/SKILL.md` 형식(frontmatter `name`/`description` + Prefer Iris Control MCP)
2. 도구는 가능하면 기존 `iris_invoke` 카탈로그 액션만 사용  
   - 새 UI 액션이 필요하면 `control_surface` 카탈로그 확장 = Core 터치 → 이슈로 먼저 합의
3. Iris 기동 시 sync가 제품 에이전트 홈(`~/.iris-light/agent` 또는 `IRIS_AGENT_HOME`)의 skills로 복사  
   - 수동: `py -3 -m iris.system.hermes_iris_control_sync --apply`
4. 스모크:

```powershell
py -3 -m iris.ui._check_control_scenarios
```

5. PR: `integrations/hermes-skills/**` + README 한 줄만. Core 경로에 diff가 있으면 리뷰어가 되묻는다.

---

## 3. 패턴 — 코드에 있는 확장 자리

교과서 클래스 이름과 1:1인 계층은 없다. 아래가 그 자리에 해당한다.

| 말한 패턴 | IRIS에서 해당하는 것 | 손대는 곳 |
|-----------|----------------------|-----------|
| 어댑터 | 외부 런타임을 Iris 호출로 바꿈 | `iris/infrastructure/*_client.py`, `iris/learning/aloha_adapter.py` |
| 전략 | 같은 사용자 턴의 실행 경로 선택 | `settings.hermes_enabled` — Iris Agent 필수 게이트(끄기 입구 차단). 엔진 소스는 InternalSidecar 기본, ExternalGateway는 env 플래그. 분기는 `iris/engine` · 채팅 워커 |
| 인터페이스 | 이름 → 핸들러. 호스트는 Protocol | `ActionRegistry.register` (`iris/system/control_surface.py`), `iris/ui/control_actions/hosts.py` |
| 감싸기 | UI 핸들러를 제어면 액션으로 감쌈 | `iris/ui/control_bindings.py`. 스킬 마크다운은 기존 `iris_invoke`를 감싼다 |

새 모델 제공자는 `*_client.py` 어댑터 하나. 새 도구는 스킬 또는 native registry. `main_window.py`에 전략 분기를 더 복사하지 않는다.

---

## 4. 어디를 고칠까

| 증상·하고 싶은 일 | 먼저 볼 곳 | 기본 태도 |
|-------------------|------------|-----------|
| 입력이 턴이 되지 않음 | `iris/runtime/user_turn_dispatcher.py` | 버그 수정 |
| 에이전트/Ollama HTTP·인증 | `iris/infrastructure/hermes_client.py`, `ollama_client.py`, `iris/engine/` | 버그 수정 |
| 설치·에이전트 기동 | `iris/system/setup_protocol.py`, `hermes_gateway.py`, `agent_runtime.py` | 버그 수정 |
| 설정이 저장되지 않음 | `iris/storage/`, `iris/config/settings.py` | 버그 수정 |
| 새 에이전트 도구 | `integrations/hermes-skills/iris-control/` 또는 `agent_tool_registry` | 코어 diff=0 우선 |
| 에이전트가 UI 버튼을 누름 | `iris/ui/control_actions/<기능>.py` | 기존 액션 재사용. 새 이름은 이슈 합의 |
| HUD 레이아웃·위젯 | `iris/ui/` 해당 하위 패키지 | UI만. GPL 유지 |
| IDE 옆 배치가 깨짐 | `iris/system/ide_tiler.py` | 정수 픽셀 8:2 유지 |
| 음성 STT/TTS | `services/voice_runtime/`, 클라이언트는 `iris/audio/` | 별도 프로세스 |
| 화면 학습 | `iris/learning/`, `integrations/showui-aloha/` | 어댑터 |
| Wiki 저장 | `iris/knowledge/` | 데이터는 여기, 페이지는 `iris/ui/workspaces` |

패키지가 무엇을 맡고 무엇을 안 하는지는 각 `iris/**/__init__.py` 의 `Agent-readable` 블록이 정본이다. `python -m pydoc iris.runtime` 로 읽는다.

---

## 5. MCP 확장

1. 가능하면 새 서버를 만들지 않는다. §2 스킬에서 기존 `iris_invoke`만 호출한다.
2. 서버가 꼭 필요하면 **별도 프로세스**(라이선스·크래시 격리). 브리지 예는 `iris/mcp/iris_control_stdio.py` → Control Surface HTTP `:8765`.
3. 에이전트 홈 `config.yaml`의 `mcp_servers`는 손으로 고치지 않는다. `hermes_iris_control_sync`가 upsert 한다.

```powershell
py -3 -m iris.system.hermes_iris_control_sync --apply
```

---

## 6. UI를 커스텀할 때

`iris/ui/`는 Core가 아니다. PyQt6라 앱 전체는 GPL이다 (`LICENSE.md` §8).

| 바꾸려는 것 | 패키지 |
|-------------|--------|
| 채팅 모양 | `iris/ui/chat/` |
| 창 크롬·메인 셸 | `iris/ui/window/` |
| 워크스페이스 페이지 | `iris/ui/workspaces/` |
| 색·글래스 | `iris/ui/shared/` |
| 툴킷 자체 (PySide6 등) | [`ui-toolkit-migration.md`](ui-toolkit-migration.md) — 문서상 경로. 제출 일정 안에서는 전환 PR을 열지 않는다 |

UI는 Gateway를 HTTP·시그널로만 부른다. 위젯 파일에 Ollama/에이전트 URL을 새로 넣지 않는다.

---

## 7. 포크 후 최소 절차

1. `setup.bat` 또는 `setup.ps1` 후 `run.bat`
2. 위 표에서 경로를 고른다
3. 패키지 docstring(`Agent-readable`)으로 경계를 확인한다
4. 스킬만 바꿨으면 Core 경로 diff가 없어야 한다 (§8)
5. `scripts\run_core_smoke.ps1`

---

## 8. “코어 불변” 자가 검증

```powershell
git diff --name-only origin/main...HEAD
# 기대(스킬만): integrations/hermes-skills/... 만
# 금지 무단: iris/runtime/, iris/system/hermes_gateway.py, iris/infrastructure/
```

예외(버그픽스·보안)는 PR 본문에 **왜 Core인지** 한 줄.
