# Extending IRIS — 코어 불변 · 확장점

| 항목 | 내용 |
|------|------|
| 목적 | 외부 기여자가 **코어 diff=0**으로 기능을 추가하는 절차 |
| 작성일 | 2026-09-23 |
| 관련 | `docs/domain.md` · `integrations/hermes-skills/README.md` · `CONTRIBUTING.md` |

---

## 1. 한 장 다이어그램

```text
┌──────────────────────────────────────────────────────────┐
│ CORE (가급적 불변)                                        │
│  iris/runtime/   UserTurnDispatcher                       │
│  iris/system/    setup_protocol · hermes_gateway · CS     │
│  iris/infrastructure/  ollama_client · hermes_client      │
│  iris/core/ · iris/storage/                               │
└───────────────┬──────────────────────────┬───────────────┘
                │ HTTP / MCP                 │ 스킬 동기화
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
| Core | 세션·Gateway·권한 경계 | **수정 최소화** — 버그/보안만 |
| Extension | 스킬 · MCP · IDE · Aloha · Voice | **여기부터 추가** |

---

## 2. 새 Hermes 스킬 추가 (코어 diff=0)

목표: `iris/runtime` · `iris/system` · `iris/infrastructure`에 **파일 변경 0**.

1. `integrations/hermes-skills/iris-control/iris-<name>/SKILL.md` 작성  
   - 기존 `iris-wiki/SKILL.md` 형식(frontmatter `name`/`description` + Prefer Iris Control MCP)
2. 도구는 가능하면 기존 `iris_invoke` 카탈로그 액션만 사용  
   - 새 UI 액션이 필요하면 `control_surface` 카탈로그 확장 = Core 터치 → 이슈로 먼저 합의
3. Iris 기동 시 `hermes_iris_control_sync`가 `%LOCALAPPDATA%\hermes\skills\`로 복사  
   - 수동: `py -3 -m iris.system.hermes_iris_control_sync --apply`
4. 스모크:

```powershell
py -3 -m iris.ui._check_control_scenarios
```

5. PR: `integrations/hermes-skills/**` + README 한 줄만. Core 경로에 diff가 있으면 리뷰어가 되묻는다.

---

## 3. MCP 확장

- stdio 브리지: `iris/mcp/`
- Hermes config의 `mcp_servers` 항목은 sync 모듈이 upsert
- 새 MCP 서버는 **별도 프로세스** 권장 (라이선스·크래시 격리)

---

## 4. UI만 바꾸는 경우

Presentation(`iris/ui/`)은 Core가 아니다. 다만 PyQt6 GPL 결합이 있으므로 라이선스 규칙을 `LICENSE.md` §8 / `CONTRIBUTING.md`에 따른다.  
툴킷 전환은 [`ui-toolkit-migration.md`](ui-toolkit-migration.md).

---

## 5. “코어 불변” 자가 검증

```powershell
git diff --name-only origin/main...HEAD
# 기대(스킬만): integrations/hermes-skills/... 만
# 금지 무단: iris/runtime/, iris/system/hermes_gateway.py, iris/infrastructure/
```

예외(버그픽스·보안)는 PR 본문에 **왜 Core인지** 한 줄.
