# Iris Agent = Hermes 기반 에이전트 — 구현 경로

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-IRIS-AGENT |
| 작성일 | 2026-10-27 |
| 관련 | 장기 목표 재정의. 이전 “엔진 소유·배포” 문서는 이 문서로 대체 |
| 대상 | Iris Light → Iris Agent (Hermes 프레임워크 기반) |
| 목적 | 목표에 맞는 구현 순서를 단계별로 고정한다 |

## 1. 결론

목표는 Iris가 Hermes를 **감싸는 앱**이 아니다.  
목표는 **Hermes를 뼈대로 새로 만든 Iris 에이전트**다.

비유.

| 잘못된 목표 | 맞는 목표 |
|---|---|
| 좋은 엔진을 사서 차에 단다 | 그 엔진 설계로 **차를 새로 만든다**. 차 이름은 Iris |
| Iris = 조종석, Hermes = 고용한 기장 | Iris = **기장 자체**. 화면은 그 기장의 얼굴 |

구현은 한 번에 합치지 않는다.  
아래 **0→5단계**를 순서대로 끝낸다.  
각 단계의 완료 기준을 통과하기 전에 다음 단계로 가지 않는다.

프로세스 하나로 합치는 것은 **5단계(선택)** 다.  
필수 조건이 아니다.

---

## 2. 지금 vs 목표 (한 장)

```
[지금]
  Iris(화면) ──HTTP──▶ Hermes(별 프로그램) ──MCP──▶ Iris(다시)
  홈 둘: ~/.iris-light  +  %LOCALAPPDATA%\hermes
  사용자 느낌: “Iris 안에 Hermes가 따로 있다”

[목표]
  Iris Agent(Hermes 기반 런타임 + Iris 도구 + Iris 얼굴)
  홈 하나(제품 이름)
  사용자 느낌: “나는 Iris라는 에이전트를 쓴다”
  고지: Nous Hermes(MIT)를 기반으로 함 (NOTICE)
```

| 항목 | 지금 | 목표 |
|---|---|---|
| 정체성 | SOUL만 Iris, 엔진 이름은 Hermes | 제품·세션·메모리 주인이 Iris Agent |
| 도구 | MCP로 Iris에 “되돌아감” | 위키·메일·IDE가 에이전트 **1급 도구** |
| 배포 | Iris 설치 + Hermes 설치/패치 | Iris Agent 한 줄 설치·업데이트 |
| 화면 | 채팅 클라이언트에 가깝다 | 에이전트의 얼굴·단축 버튼 |
| 클릭 | Hermes 안 탐 (유지) | 유지. 클릭까지 모델에 태우지 않음 |

---

## 3. 구조 (말·클릭이 가는 길)

### 3.1 지금

```
말 → Iris 채팅 → :8642 Hermes → MCP iris-control → :8765 Iris 핸들러
클릭 → Iris 사이드바 → 같은 핸들러 (Hermes 없음)
```

### 3.2 목표 (4단계 이후)

```
말 → Iris Agent 루프(Hermes 기반)
        ├─ Iris 1급 도구 (위키·메일·IDE·…)
        └─ LLM (Ollama 등)
클릭 → Iris 화면 단축 → 같은 도구 핸들러 (에이전트 턴 없음)
```

갈림.

| 선택 | 판단 |
|---|---|
| 클릭도 에이전트에 태운다 | **하지 않음** |
| 처음부터 Qt에 루프를 import | **하지 않음** (5단계에서만 검토) |
| Hermes 없이 루프를 새로 짠다 | **하지 않음** (기반이 Hermes여야 함) |

---

## 4. 구현 순서

### 0단계. 목표 문장 고정

**결과.** 팀·문서·이슈가 같은 문장을 쓴다.

> Iris Agent는 Hermes 프레임워크를 기반으로 한 에이전트 제품이다.  
> Iris는 Hermes의 클라이언트 껍질이 아니다.

**하는 일.**

1. 이 문서를 유일한 경로 문서로 둔다.
2. UI/설정 카피에서 “Hermes 연결” 대신 “Iris Agent / 에이전트 런타임”으로 바꿀 목록을 만든다. (이 단계에서 문구만 목록화. 실제 교체는 1단계.)

**완료 기준.**

- [ ] 목표 문장이 이 문서 §1과 동일하다.
- [ ] “엔진 소유·배포가 곧 일체화”라는 문장을 쓰지 않는다.

---

### 1단계. Iris Agent 런타임으로 이름·집을 바꾼다

**결과.** 디스크와 제품 언어에서 “별도 Hermes 앱”이 사라지기 시작한다.  
코드 뼈대는 아직 Hermes다. **주인공 이름만 Iris Agent**로 바꾼다.

**하는 일.**

1. Hermes 소스의 **Iris 전용 기준선**을 만든다. (GitHub fork 또는 `vendor/iris-agent-runtime`.)
2. 설치·업데이트가 upstream `main`이 아니라 **이 기준선 SHA**만 쓰게 `hermes_install` / `hermes_update`를 고친다.
3. 런타임 홈을 제품 경로로 옮기거나 별칭한다.  
   예: `~/.iris-light/agent` (또는 `IRIS_AGENT_HOME`).  
   `%LOCALAPPDATA%\hermes`는 호환용으로만 남기거나 이전 후 폐기한다.
4. soft-patch 3종을 **기준선 커밋**으로 넣는다.  
   - ollama options guard  
   - stdio dead-check  
   - terminal / browser disable 정책  
5. `LICENSE.md` §3.4와 NOTICE를 “기반 사용 + MIT 고지”에 맞게 고친다. **in-tree vendor vs out-of-tree fork를 이 단계 전에 하나로 고른다.**
6. UI 일상 문구(“Iris Agent 준비됨”)는 **아직 바꾸지 않는다.** (2단계 뒤. 구조 없이 브랜드만 바꾸면 가짜 완료가 됨.)

**손대는 곳 (예상).**

- `iris/system/hermes_install.py`, `hermes_update.py`, `hermes_gateway.py`
- `iris/infrastructure/hermes_credentials.py` (`hermes_home`)
- `iris/system/hermes_ollama_guard.py`, `hermes_iris_control_sync.py`
- `LICENSE.md` / NOTICE

**완료 기준.**

- [ ] `git rev-parse HEAD` == pin. 설치 origin이 Nous `main` floating이 아니다.
- [ ] soft-patch가 기준선 테스트로 고정돼 update 후 재치환이 없다.
- [ ] 새 PC에 Iris만 설치해도 런타임이 뜬다. (UI 브랜드 교체는 아직 필수 아님.)
- [ ] 포크 리베이스·CVE 추격 절차 문서 1장.

---

### 2단계. 경계를 뒤집는다 (도구가 Iris의 것이 된다)

**결과.** “Hermes가 Iris를 원격 조종”이 아니라  
“**Iris Agent가 Iris 도구를 부른다**”가 된다.

**하는 일.**

1. Control Surface(`:8765`) + MCP 3도구를 **임시 다리**로 유지한 채, 의미를 재정의한다.  
   문서·스킬·넛지 문장: “외부 앱 제어” → “Iris Agent 툴 어댑터”.
2. 위키·메일·캘린더·IDE·프로젝트 실행을 **에이전트 툴 카탈로그**로 정리한다.  
   지금 `iris_invoke(action=…)` 147개를 그대로 쓰되, 스킬은 “Iris 도구 사용법”으로 다시 쓴다.
3. MCP 왕복을 줄일 **다음 형태**를 고른다. (이 단계에서 하나 확정.)

| 형태 | 내용 | 2단계 완료? |
|---|---|---|
| A. 네이티브 툴 + IPC | 포크 **tool registry**에 Iris 도구 등록. MCP stdio 제거. 전송은 IPC(또는 동등). 핸들러 모듈은 기준선 소유 | **예 (필수)** |
| B. 이름만 바꾼 MCP | `iris-tools` 등. `:8765` 왕복 유지 | **아니오 (미완료)** |

3. B로 멈추지 않는다. A만 2단계 통과다.  
   **Phase 2.5 (2026-10-27):** 제품 `_SEED` 전원 native + speak/MCP redirect. 비-시드 `:8765`는 compat only. → §10.1 gate 1 CLOSED. (147 MCP 전체 삭제 아님.)

4. SOUL에서 “너는 Hermes가 아니다” 부정문을 지우고 Iris 정체성만 남긴다.  
   스킬·툴 description·`hermes_online` 사용자 노출을 제거한다.  
   세션 DB 정본(Iris vs 런타임)을 한쪽으로 고른다.

**손대는 곳 (예상).**

- 포크 tool registry, `integrations/hermes-skills`, `hermes_memory_nudge.py`, SOUL
- MCP 제거 또는 개발용만 유지
- control_actions는 실행 본체. **등록 위치**는 포크 쪽

**완료 기준.**

- [ ] 말 턴 프로세스에 MCP stdio + `:8765` 왕복이 없다. (관측)
- [ ] 스킬에 `mcp__iris_control__` / 사용자 문구 `Hermes` = 0
- [ ] 사이드바 클릭은 에이전트 턴을 만들지 않는다.

---

### 3단계. 화면을 에이전트에 종속시킨다

**결과.** Qt는 **에이전트의 얼굴**이다.  
채팅 창이 “외부 엔진 클라이언트”가 아니다.

**하는 일.**

1. 채팅 경로 이름을 HermesClient/HermesChatWorker에서 Iris Agent 쪽으로 바꾼다. (동작 동일해도 이름·패키지 정리.)
2. 기동 순서를 “Iris Agent supervisor” 한곳으로 모은다.  
   → Phase 4b: `ensure_iris_agent_runtime` (setup + HealthWorker + login warm).  
   목표 잔여: Ollama·Control/툴 브리지도 같은 수명 문서 아래 정리.
3. Live Activity·도구 진행 UI를 “Iris가 도구를 쓰는 중”으로 표시한다.
4. 설정에 “에이전트 버전”(런타임 pin SHA/태그)만 노출한다.
5. 설정·상태 UI에서 Hermes **클라이언트 껍질을 제거한다** (숨김 금지).  
   삭제 대상 예: “Hermes API URL”, “Hermes API Key”, “Hermes 명령”, “연결 (Ollama / Hermes)” 식 라벨, Hermes gateway 연결 칩 문구.  
   키·URL은 supervisor/런타임 홈 `.env`가 소유. 사용자가 입력하는 Hermes 전용 필드는 **없어야** 한다.  
   NOTICE/라이선스 고지 화면의 “Hermes Agent by Nous Research (MIT)”만 남긴다.

**완료 기준.**

- [ ] 설정 대화상자에 Hermes URL/Key/명령 입력 위젯이 **없다** (숨김이 아님. 코드·UI 트리에서 제거).
- [ ] 사용자 문서·토스트·칩에 Hermes gateway 포트·별도 설치 설명이 없다. (NOTICE만.)
- [x] Iris를 끄면 에이전트 런타임 수명 정책이 제품 규칙으로 문서화되어 있다. → **keep-background** (Phase 4b).

---

### 4단계. 배포·기억을 한 제품으로 묶는다

**결과.** 설치·업데이트·데이터가 **Iris Agent 하나**다.

**하는 일.**

1. Iris 설치/업데이트 UX가 런타임 버전을 함께 올린다.
2. `%LOCALAPPDATA%\hermes` 잔여 경로를 마이그레이션 스크립트로 `IRIS_AGENT_HOME`으로 옮긴다.
3. MEMORY vs Iris DB/위키의 **역할**을 표로 고정한다. (한꺼번에 합치지 말 것.)

| 기억 | 주인 | 용도 |
|---|---|---|
| Iris Agent MEMORY/USER | 런타임 | 페르소나·선호·짧은 학습 |
| Iris SQLite `chat_messages` | Iris 제품 | **사용자 보이 채팅 정본** |
| 런타임 session DB | 런타임 | 루프 ephemeral. UI 정본 아님 |
| Iris 위키 / 메일 / 일정 | Iris 제품 | 노트·메일·일정·프로젝트 사실 |

4. Ollama는 계속 별 프로세스여도 된다. “두뇌”는 에이전트 밖이어도 제품 문장에 넣지 않는다.

**완료 기준.** (Phase 4 코드: `Iris-Agent-home-Phase4.md`)

- [x] 제품 홈 `iris_agent_home()` = `IRIS_AGENT_HOME` \| `~/.iris-light/agent` (레거시 폴백 제거)
- [x] 구 Hermes 홈 → 제품 홈 멱등 마이그레이션 (원본 보존)
- [x] 채팅 정본 = Iris SQLite (`chat_canonical`)
- [x] supervisor 완전 합류 (`ensure_iris_agent_runtime` — Phase 4b / gate 4 CLOSED)
- [ ] 클린 설치 E2E 수동 (도구·위키) — 코드 게이트와 별도

일체화 완료 가능: §10.1 게이트 1~4 전부 CLOSED (Phase 2.5 seed native + Phase 4b supervisor). Phase 5는 선택.

---

### 5단계. (선택) 한 프로세스로 넣을지 검증한다

**결과.** 넣거나, **넣지 않기로 확정**한다.

**하는 일.**

1. 프로토타입: agent loop를 Qt와 같은 프로세스에서 돌린다. (또는 같은 프로세스 내 서브인터프리터/스레드 — 조사 후 하나.)
2. 검증 항목.

| 항목 | 실패하면 |
|---|---|
| Qt 슬롯 예외 / 0xC0000409 | 병합 보류 |
| 콘솔 창 깜빡임 | 병합 보류 |
| 에이전트 크래시가 Iris 전체 종료 | 병합 보류 또는 격리 재설계 |
| 디버그·재시작 비용 | 자식 프로세스 유지가 나을 수 있음 |

3. 프로세스가 둘이어도 된다. **조건은 §10.1 소유권 게이트 4개 충족**이다.  
   게이트 미달인 채 “이름만 Iris”인 자식 프로세스는 일체화 성공이 **아니다**.

**완료 기준.**

- [ ] “병합한다 / 안 한다” + 증거가 한 줄로 남는다.
- [ ] 안 병합이어도 §10.1 게이트는 이미 통과한 상태다.

---

## 5. 코드 리뷰 (지금 막히는 지점)

| 지점 | 파일 | 지금 하는 일 | 목표를 막는 이유 |
|---|---|---|---|
| 설치 | `hermes_install.py` | upstream main clone | Iris Agent 기준선이 없음 |
| 업데이트 | `hermes_update.py` | origin/main 추격 | 제품 버전이 아님 |
| 홈 | `hermes_credentials.py` | `%LOCALAPPDATA%\hermes` | 이중 세계 |
| sync | `hermes_iris_control_sync.py` | 외부 디스크에 MCP·스킬 주입 | “남 집에 세간 놓기” |
| soft-patch | ollama guard, dead-check, terminal policy | 설치본 문자열 치환 | 기반 코드가 Iris 것이 아님 |
| 채팅 | `hermes_client.py`, workers | 외부 HTTP 클라이언트 | 클라이언트 껍질 구조 |
| 역제어 | MCP → Control Surface | Hermes가 Iris를 부름 | 주객이 뒤집힘 |
| 라이선스 | `LICENSE.md` §3.4 | 번들 안 함·별도 프로세스 | 기반 제품 선언과 어긋남 |

하지 않은 일 (이 문서 범위).

- 코드 변경·포크 생성
- in-process 프로토타입
- completed/ 아래 Hermes 채팅 400·401·설치 버그 문서 삭제 (별 주제)

---

## 6. 개선안 (빈자리)

| 빈자리 | 메우는 단계 |
|---|---|
| 제품 주인공이 Hermes | 0~1 |
| 도구가 “되돌아오는” 구조 | 2 |
| UI가 외부 엔진 클라이언트 | 3 |
| 이중 홈·이중 설치 | 1·4 |
| 프로세스 병합 여부 미정 | 5 |

---

## 7. 차용

| 이름 | 가져올 부분 | 가져오지 않는 이유 |
|---|---|---|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT) | agent loop, skills, memory, MCP host, gateway 계약 | 통째로 “Hermes 앱”으로 남기지 않음. **Iris Agent의 뼈대**로만 |
| agentskills.io | 스킬 형식 | 그대로. 내용은 Iris 도구 절차로 재작성 |
| MCP | 2단계 중간 다리 | 최종은 내장 브리지 우선 |
| OpenAI Completions | 얼굴↔런타임 임시 HTTP | 2~3단계에서 내부 API로 축소 가능 |
| 찾지 못함 | 동일 제품(데스크톱 HUD + Hermes급 에이전트) 레퍼런스 | — |

---

## 8. 단계 한눈에

| 단계 | 한 줄 | 완료하면 사용자가 느끼는 것 |
|---|---|---|
| 0 | 문장 고정 | “Iris Agent를 만든다”로 말이 같다 |
| 1 | 이름·집·pin | Hermes 따로 설치 안 함 |
| 2 | 도구 주객 전환 | Iris가 도구를 쓰는 에이전트 |
| 3 | 화면 종속 | 채팅이 곧 Iris Agent |
| 4 | 배포·기억 정리 | 설치·데이터가 하나 |
| 5 | (선택) 프로세스 | 증거 보고 병합 여부 결정 |

---

## 9. 조치

1. 이 문서를 Iris↔Hermes 일체화의 **유일한 경로 문서**로 쓴다.
2. 다음 구현은 **1단계**(기준선 pin + soft-patch 흡수 + 홈 env 통일)부터. **UI 브랜드·Hermes 필드 제거는 2 뒤 3단계(제거만)**.
3. 2단계 완료는 **A만** 인정한다. B(이름만 바꾼 MCP)는 미완료. 3단계는 Hermes URL/Key/명령 **숨김 금지·제거만**.
4. 5단계는 1~4 소유권 게이트를 통과한 뒤에만. 5단계 실패를 일체화 성공으로 쓰지 않는다.
5. 클릭을 에이전트 턴으로 보내는 작업은 범위 밖.
6. 새 `hermes_*` 모듈·기동 경로 추가 금지(login warm 등은 3단계 supervisor로만).

---

## 10. 다중 검토 반영 (2026-10-27)

| 항목 | 내용 |
|---|---|
| 검토 | Interrogate. Reviewer A (Claude Opus), Reviewer B (Grok). 계획 문서 + 현 코드 |
| Hermes 런타임 | 업데이트 적용. `d02f211` → `a382af2` (= origin/main). gateway health OK |
| soft-patch | ollama options guard 유지. dead-check는 업스트림이 극성 수정함 → Iris 패치 skip이 정상 |

### 10.1 합의 판정

**§10.1 게이트 1~4 CLOSED (2026-10-27 Phase 2.5 + 4b).**  
제품 경로의 툴 소유권·설정·채팅 정본·supervisor가 Iris Agent다. 비-시드 Control HTTP는 compat only. Phase 5(in-process)는 선택.

일체화 성공의 **소유권 게이트** (프로세스 수와 무관).  
상태 (2026-10-27 Phase 2.5): 1 **CLOSED** · 2 **CLOSED** · 3 **CLOSED** · 4 **CLOSED**.  
→ **일체화 완료** (§11; Phase 5 in-process는 선택).

1. 툴 정의·registry가 Iris Agent 기준선(포크) **안에** 있다. MCP로 Qt에 되돌아오는 경로가 제품 경로가 아니다. → **CLOSED** (Phase 2.5: `_SEED` mcp_bridge=0; speak/native = IrisAgentToolRegistry; 비-시드 `iris_invoke`→`:8765`는 **compat only**; 147 MCP 전체 삭제 아님; plan B 금지)
2. 런타임 설정을 Iris가 **생성**한다. `config.yaml` upsert/patch 코드가 0에 수렴한다. → **CLOSED** (Phase 3 설정 필드 삭제)
3. 대화 기록 정본이 하나다. (Iris DB vs 런타임 session DB) → **CLOSED** (`chat_canonical` = Iris SQLite)
4. supervisor 하나가 수명을 관리한다. → **CLOSED** (`ensure_iris_agent_runtime`; setup/Health/warm 합류; lifetime=keep-background)

### 10.2 계획 수정 (강제)

| 문제 | 수정 |
|---|---|
| 2단계 A(내장) vs 자식 프로세스 모순 | A = 포크 **네이티브 툴 registry** + IPC. “로컬 함수만”이 아님. B는 2단계 미완료 |
| 5단계 실패 = 성공 인정 | 삭제. 1~4 소유권 게이트 미달이면 미완료 |
| 1단계에서 UI “Iris Agent 준비됨” | 2단계 뒤로 이동. 1단계는 pin·패치·홈 env만 |
| 완료 기준이 “설명 가능/느낌” | 관측 가능 명령으로 교체 (아래) |
| Hermes-free 이름 | UI만으로는 불가. SOUL·스킬·툴 schema·프로세스명·에러 문자열까지 목록화 |

### 10.3 Hermes 없는 이름 — 가능 범위

| 층 | Hermes 제거 | 비고 |
|---|---|---|
| 설정/채팅 UI 라벨 | 가능·해야 함 | 지금은 “Hermes API URL” 등 다수 |
| 스킬 본문·SOUL | 가능·해야 함 | `hermes_online`, “Hermes terminal”, “너는 Hermes가 아니다” |
| MCP 툴 접두사 `mcp__iris_control__` | 2단계 A에서 제거 | Live Activity에도 노출 |
| 코드 심볼 `hermes_*` | 점진 rename | 내부. 사용자 비노출이면 후순위 |
| NOTICE / LICENSE 원본 | **유지** | MIT. “Hermes Agent by Nous Research” |
| 프로세스 `hermes_cli` | 포크·엔트리 이름 변경 시 | 작업 관리자에 보임 |

### 10.4 관측 가능 완료 예 (단계별에 넣을 것)

- `git -C <agent> rev-parse HEAD` == pin. origin이 Nous `main` 추격 아님.
- 제품 경로에 `%LOCALAPPDATA%\hermes` 미사용 (이전 후).
- 스킬·UI 사용자 문자열 `rg -i hermes` = 0 (NOTICE 제외).
- 말 턴에 MCP stdio + `:8765` 왕복 없음 (2단계 A).
- `config.yaml` Iris upsert 호출 경로 제거 또는 생성 전용 API만.

---

## 11. 장기 전제: Hermes 전면 흡수 후 초파리 확장

| 항목 | 내용 |
|---|---|
| 지금 목표 | Iris와 Hermes의 **완벽한 일체화**. Hermes의 기능·구조(루프·툴·스킬·메모리·MCP 호스트·gateway 계약)를 Iris Agent가 **전부 가진 상태** |
| 그다음 | 그 위에 초파리 뇌를 라우터·내부 기능으로 **확장** (Hermes를 버리는 교체가 아님) |
| 잘못된 축소 | “Hermes는 임시 뼈대 → 일부만”은 **폐기**. 전면 흡수가 전제다 |

### 11.1 층 (흡수 완료 후)

```
[입력] 말 / 클릭
   → [확장 슬롯]  ← 나중: 초파리 뇌 (라우터·회로 on/off)
   → [Iris Agent 코어]  ← 지금: Hermes 전면 흡수본 (루프·스킬·메모리·툴 호스트)
   → [Iris 도구·얼굴]   위키·메일·IDE·Qt
```

초파리는 **흡수 완료된 Iris Agent 위**에 얹는다.  
흡수 전에 초파리 슬롯만 파고 Hermes를 얇게 두는 경로는 쓰지 않는다.

### 11.2 완벽한 일체화 = 이 문서 0→4 + §10.1 게이트 (필수)

| 단계 | 완벽한 일체화에서 | 비고 |
|---|---|---|
| 0 | 문장 고정 | “Iris Agent = Hermes 전면 흡수 제품” |
| 1 | pin·포크·soft-patch 흡수·홈 제품화 | 브랜드 UI는 2 뒤 |
| 2 | **A만** (네이티브 툴 registry + MCP 제품 경로 제거) | B는 일체화 미완료 |
| 3 | 화면·기동 supervisor가 Iris Agent | Hermes 클라이언트 껍질 제거 |
| 4 | 배포·기억·세션 정본 한 제품 | |
| 5 | in-process | **선택**. 게이트 1~4만으로도 “완벽” 가능. 증거 후 |

§10.1 소유권 게이트 4개를 통과하기 전에는 일체화 완료라고 하지 않는다.

### 11.3 진행 순서 (지금: 일체화만)

1. **0** — 목표 문장을 §11과 같게 고정. 초파리 구현은 백로그만.
2. **1** — Iris Agent 기준선(포크/vendor) + pin + soft-patch 커밋 + 홈/설치가 그 트리만 씀. UI 브랜드 문구는 아직 안 바꿈.
3. **2 A** — Hermes 구조(루프·스킬·메모리·MCP 호스트)는 유지·흡수. Iris 도구는 포크 registry 1급. 제품 경로에서 MCP→`:8765` 역제어 제거.
4. **3** — 채팅·기동·상태 UI가 Iris Agent. Hermes URL/Key/명령 **필드·라벨·칩을 제거** (숨김 금지).
5. **4** — 한 설치·한 홈·기억/세션 정본.
6. **§10.1 게이트 검증** — 통과 시에만 “일체화 완료”.
7. **5 (선택)** — in-process prove. 실패해도 1~4+게이트면 일체화는 유지.
8. **그다음 에픽** — 초파리 뇌 확장 (이 문서 범위 밖).

### 11.4 왜 이 순서인가

- Hermes **기능·구조 전부**를 가지려면 soft-fork·역제어·이중 홈을 끝내야 한다. 그게 1→4다.
- 이름만 바꾸거나 MCP B로 멈추면 “전면 흡수”가 아니다. 다중 검토(§10)와 동일.
- 초파리는 흡수본 **확장**이므로, 일체화 미완성 상태에서 라우터만 넣으면 두 과제가 섞인다. **일체화 먼저, 초파리는 다음 에픽.**
