# Iris Agent Phase 5 — in-process 검증 계획 (병합 전)

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-10-27-AGENT-P5-PROVE |
| 작성일 | 2026-10-27 |
| 관련 | `completed/Iris-Agent-Hermes기반-구현경로.md` §4 5단계, §10.1(이미 CLOSED) |
| 대상 | 프로세스 병합 **여부·방법**을 증거로 확정 |
| 목적 | 합치되 단점을 막아 가며, **바로 병합하지 않고** 단계 테스트 후 진행 |

## 1. 결론

제품·도메인 면에서는 **합치는 쪽이 맞다.**  
코드 품질·확장성은 **폴더/패키지 분리 + 스레드 경계**로 지킨다.  
지금 하는 일: 병합 코드 전면 투입이 아니라, 아래 **Prove 0→4**를 새 채팅마다 하나씩 통과시킨 뒤, 전부 통과할 때만 “병합 착수” 채팅을 연다.

단점 대응 요약.

| 단점 | 대응 |
|---|---|
| 슬롯 abort·프리즈 | 에이전트는 Qt 위젯 금지. 워커 스레드 + 시그널만 |
| 엔진 예외 = 전체 죽음 | 루프 예외는 잡혀 “에이전트 오류”로. 네이티브 abort는 자검 필수 |
| 엔진만 핫리스타트 어려움 | in-process **루프 리셋 API**를 supervisor에 두고 프로세스 재시작 대체 |
| 폴더가 섞임 | `iris/agent/`(루프) · `iris/ui/`(얼굴) · registry/runtime 유지 |
| 콘솔 깜빡임 | no-console 계약 + prove 자검 |

Ollama는 합치지 않는다 (계속 별 프로세스 허용).

---

## 2. 용어 (쉽게)

### pin
설치·업데이트가 따라갈 **런타임 Git 커밋 SHA를 고정**한 값이다.  
파일: `vendor/iris-agent-runtime/PIN`.  
Nous `main`을 흘러가지 않고, Iris가 고른 버전만 쓴다.  
Phase 5와 직접 무관하지만, 합쳐도 **같은 pin 기준선**을 import한다.

### 슬롯 abort
PyQt에서 버튼·타이머 등이 연결한 함수(슬롯) 밖으로 Python 예외가 새면, 오류 창 없이 Iris가 **즉시 종료**되는 현상이다 (`0xC0000409`).  
“에이전트가 죽으면 고친다”와 별개로, **UI 스레드에서 예외가 새면 앱이 바로 죽는다.**

### 프리즈
UI 스레드가 오래 막히면 창이 “응답 없음”처럼 멈춘다.  
에이전트 루프·LLM 대기를 **UI 스레드에서 돌리면** 프리즈가 난다.

### 스레드 경계
**같은 프로세스 안**에서도 일을 나눈다.

| 스레드 | 하는 일 | 하지 않는 일 |
|---|---|---|
| UI (메인) | 그리기, 클릭, 슬롯 | LLM 루프, 긴 디스크/네트워크 대기 |
| Agent 워커 | 에이전트 루프, 툴 native 호출 | `QWidget` 생성·직접 조작 |

나누는 이유: 프로세스를 합쳐도 Qt 이벤트 루프와 에이전트 루프가 섞이면 abort·프리즈가 난다.  
나누는 방법: 지금 `HermesChatWorker(QThread)`처럼 워커에서 돌리고, 결과는 `pyqtSignal`로만 UI에 전달. Phase 5 prove도 이 계약을 강화한다.

```
[한 프로세스 Iris.exe]
  UI 스레드 ──signal──▶ 화면
       ▲
       │ signal (chunk / done / error)
  Agent 워커 스레드 ──▶ 루프·툴 (위젯 금지)
```

---

## 3. 엔진만 핫리스타트가 필요한 경우

별 프로세스일 때 “엔진만 재시작”하던 상황을, 합친 뒤에는 **루프 리셋**으로 대체해야 한다.

| 상황 | 지금(별 프로세스) | 합친 뒤 목표 |
|---|---|---|
| gateway 응답 없음 / 포트 꼬임 | gateway 재기동 | in-process 루프 인스턴스 dispose → 새로 생성 |
| MCP·스킬 sync 후 재연결 | gateway reload | 툴 registry / 세션 상태 리셋 (HTTP reload 불필요) |
| 모델·provider `.env` 변경 | gateway 재시작 | 설정 reload + 루프 재생성 |
| soft-hang (루프만 멈춤, UI는 살아 있음) | 엔진 kill | 워커 cancel + 새 워커 (UI 유지) |
| pin/런타임 코드 교체 | 엔진 재설치·재기동 | **프로세스 재시작이 필요할 수 있음** (코드 리로드 한계) — prove에서 명시 |
| Ollama 다운 | 엔진과 무관 | 그대로 Ollama만 다룸 |

Prove에서 반드시 확인할 것: **“UI는 유지한 채 에이전트 워커만 교체”**가 되는가.

---

## 4. 구조 (검증이 가는 길)

```
새 채팅 Prove 0  라이브러리·루프를 UI 없이 워커에서 import/1턴 스모크
     │
새 채팅 Prove 1  슬롯 abort·프리즈 계약 (예외가 UI로 안 샘, UI 스레드 블로킹 없음)
     │
새 채팅 Prove 2  no-console + 예외 봉쇄 (에이전트 예외 → failed 시그널, 프로세스 생존)
     │
새 채팅 Prove 3  루프 리셋(핫리스타트 대체) + pin 동일성
     │
전부 PASS
     │
새 채팅 Merge   :8642 제품 경로 강등·in-process 기본화 (이 문서 “착수 조건” 충족 시만)
```

갈림: Prove 중 하나라도 FAIL → 병합 착수 금지. 고치고 해당 Prove 채팅만 다시.

---

## 5. 코드 리뷰 (현재 기준점)

| 지점 | 지금 | Prove에서 확인할 것 |
|---|---|---|
| `HermesChatWorker` | 이미 QThread + signal | in-process 루프도 여기(또는 후속 `AgentLoopWorker`)만 |
| `HermesClient.stream_chat` | HTTP `:8642` | Prove 0은 **대체 호출면**만 스모크. 전면 삭제 금지 |
| `ensure_iris_agent_runtime` | 홈+gateway supervisor | 리셋 API 후보로 확장 여부만 문서·스텁 |
| `IrisAgentToolRegistry` | native seed | 워커 스레드에서 호출 시 Qt 금지 유지 |
| MainWindow 슬롯 | abort 민감 | Prove 1에서 “워커→잘못된 UI 직접 호출” 금지 assert |

하지 않은 일(이 문서 범위): `:8642` 제거, 전면 import 병합, 초파리, git commit.

---

## 6. 개선안 (단점 보완하며 합치는 방법)

1. **패키지** — 루프는 `iris/agent/`(또는 기존 infrastructure 하위)에 두고 UI와 import 방향은 `ui → agent`만. `agent → ui` 위젯 import 금지.
2. **스레드** — 루프·툴은 워커만. UI는 signal 슬롯만.
3. **예외 계약** — 워커 `run()` 최외곽 try/except → `failed.emit`. 슬롯은 얇게.
4. **리셋** — `reset_agent_loop()`: cancel worker, clear session ephemeral, new worker. UI/MainWindow 유지.
5. **게이트웨이** — Prove 통과 전 `:8642` 유지(폴백). Merge 채팅에서만 제품 기본 경로를 in-process로.
6. **pin** — in-process여도 로드하는 코드/vendor는 `PIN` SHA와 일치한다고 자검.

---

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| 현재 `HermesChatWorker` | QThread + pyqtSignal 패턴 | 새 프레임워크 불필요 |
| Qt `QThreadPool` / `QtConcurrent` | — | 기존 워커 패턴과 이중화 |
| Python `concurrent.futures` | 루프 쪽 순수 실행 | UI 연동은 Qt signal이 이미 있음 |
| 별 프로세스 sandbox | 크래시 격리 | 제품 합침 목표와 반대. 예외 봉쇄로 대체 |
| Ollama 서버 | 외부 LLM | 합침 대상 아님 |

---

## 8. Prove 진행 (채팅마다 해당 칸만)

- [x] Prove 0 — 워커 스탠드인 + QWidget 금지 자검 (`_check_iris_agent_phase5_prove0`, 보고서 `Iris-Agent-Phase5-prove0.md`). HTTP `:8642` 미사용(stub). Merge 금지.
- [x] Prove 1 — 스레드 경계·시그널만 (`_check_iris_agent_phase5_prove1`, 보고서 `Iris-Agent-Phase5-prove1.md`). Merge 금지.
- [x] Prove 2 — no-console + 예외 봉쇄 (`_check_iris_agent_phase5_prove2`, 보고서 `Iris-Agent-Phase5-prove2.md`). Merge 금지.
- [x] Prove 3 — 루프 리셋 + pin 동일성 (`_check_iris_agent_phase5_prove3`, 보고서 `Iris-Agent-Phase5-prove3.md`). **Merge allowed? YES** (prove 게이트). Merge 채팅 미착수.

## 9. 착수 조건 (Merge 채팅 열기 전)

- [x] Prove 0~3 자검 전부 PASS (보고서·로그에 한 줄씩)
- [x] “UI 유지 + 워커 리셋” 시나리오 PASS
- [x] 슬롯 abort 재현 테스트가 의도적으로 실패하지 않음 (워커 경로)
- [x] no-console 관련 기존 unittest 회귀 없음
- [ ] 사용자가 Merge 채팅을 **명시적으로** 연다

**Merge allowed? YES** — Prove 0~3 게이트 충족. 위 마지막 칸(사용자 명시 Merge 채팅)이 열리기 전에는 Merge 코드 경로를 바꾸지 않는다.

실패 시: 병합하지 않고 별 프로세스 유지가 기본. 일체화(§10.1)는 이미 완료 상태 유지.

## 10. 조치

1. 용어·핫리스타트·본 계획: 이 문서.
2. 구현 프롬프트(전체 Goal): `docs/prompts/Iris-Agent-Phase5-in-process-구현프롬프트.md`
3. 새 채팅용 단계 본문: `docs/prompts/Iris-Agent-Phase5-prove-채팅시퀀스.md`
4. **계획·프롬프트 작성 채팅에서는 병합·Prove 실행 없음.** Prove 0부터 **새 채팅**에서만 실행.
