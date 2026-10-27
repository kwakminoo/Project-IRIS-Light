# Prompt: Iris Agent = Hermes 전면 흡수 일체화

기준 문서: `docs/code-review/Iris-Agent-Hermes기반-구현경로.md` (특히 §1, §4, §9, §10.1, §11).

장기: 초파리 뇌는 **이 일체화 완료 후** 확장 에픽. 이번 프롬프트 범위 밖.

```text
Context:
- 지금: Iris(Qt) ──HTTP :8642──▶ Hermes(별 프로세스·%LOCALAPPDATA%\hermes) ──MCP──▶ Iris :8765
- soft-fork: ollama options guard는 설치본에 있음. dead-check는 업스트림 수정으로 Iris 패치 skip이 정상.
- Hermes 런타임은 이미 origin/main(a382af2)까지 맞춤.
- 목표: Iris Agent가 Hermes의 기능·구조(루프·툴셋·스킬·메모리·MCP 호스트·gateway 계약)를
  전면 흡수한 한 제품. “이름만 바꾼 감싸기”·MCP B안·설정 필드 숨김은 실패.
- §10.1 소유권 게이트 4개 통과 전 “일체화 완료” 금지.
- 3단계: Hermes API URL/Key/명령·관련 칩·라벨은 **제거**만. 숨김 금지. NOTICE의 MIT 고지만 남김.

Goal (순서 고정, 단계마다 검증 후 다음):

0) 목표 문장·이 프롬프트·경로 문서를 구현 기준으로 고정. 초파리 코드 넣지 않음.
1) Iris Agent 기준선
   - GitHub fork 또는 vendor/iris-agent-runtime 중 하나 확정(LICENSE §3.4/§3.3 같이 개정).
   - hermes_install / hermes_update가 Nous floating main이 아니라 pin SHA만 쓰게 변경.
   - soft-patch(ollama options, terminal/browser policy 등)를 기준선 커밋+테스트로 흡수.
     런타임 문자열 치환에 의존하지 않음.
   - 홈: IRIS_AGENT_HOME(또는 ~/.iris-light/agent)로 제품화. 설치·gateway·sync·warm이 한 함수의 홈만 씀.
   - UI 브랜드(“Iris Agent 준비됨”)는 아직 대규모 교체하지 않음(2 뒤).
2) 도구 주객 A만
   - Hermes 루프·스킬·메모리·MCP 호스트 구조는 기준선 안에 유지·소유.
   - Iris 위키·메일·IDE 등 도구는 포크 네이티브 tool registry에 등록.
   - 제품 채팅 경로에서 MCP stdio → :8765 역제어 제거(관측 가능).
   - B(이름만 iris-tools MCP)로 2단계 완료 처리 금지.
   - SOUL “너는 Hermes가 아니다” 부정문 삭제. Iris 정체성만. 스킬 사용자 문구 Hermes=0.
3) 화면·기동 완전 일체화 (제거)
   - HermesClient/HermesChatWorker 등 공개 이름을 Iris Agent 쪽으로.
   - setup + HealthWorker + login warm → Iris Agent supervisor 한곳.
   - 설정 UI에서 Hermes API URL / API Key / Hermes 명령 / “Ollama / Hermes” 연결 라벨·
     Hermes gateway 칩 문구를 **코드에서 삭제**. 위젯 hide 아님.
   - 설정에는 에이전트 버전(pin)·Ollama 등 제품 필드만.
   - NOTICE에만 “Hermes Agent by Nous Research (MIT)”.
4) 배포·기억
   - 설치/업데이트가 런타임 pin을 함께 올림.
   - 구 %LOCALAPPDATA%\hermes 마이그레이션 → 제품 홈. 옛 .env/bak 잔존 없게.
   - 대화 기록 정본 하나(Iris DB vs 런타임 session) 문서+코드로 고정.
5) (선택, 게이트 후) in-process prove. 실패해도 1~4+§10.1이면 일체화 유지 가능.

Constraints:
- 클릭·사이드바를 에이전트 턴으로 보내지 않음.
- 새 hermes_* 모듈·기동 경로 추가 금지. login warm은 supervisor로만 흡수.
- no-console-windows, qt-slot-abort, iris-exe thin launcher 계약 유지.
- 커밋은 사용자 요청 있을 때만. 단계마다 검증 스크립트/assert 남김.
- 단계 순서를 건너뛰지 않음. 1 미완으로 2/3 브랜드·제거 대규모 착수 금지.

Interface / 손댈 곳 (1단계부터):
- iris/system/hermes_install.py, hermes_update.py, hermes_gateway.py
- iris/infrastructure/hermes_credentials.py (홈 단일화)
- iris/system/hermes_ollama_guard.py, hermes_iris_control_sync.py
- LICENSE.md
- 이후 2: 포크 tool registry, integrations/hermes-skills, SOUL, mcp 경로
- 이후 3: iris/ui/settings/settings_dialog.py, hermes_login_warm_box, chat 칩,
  workers 이름, control_actions settings summaries

검증 (단계별 최소):
1) git -C <agent> rev-parse HEAD == pin; update가 pin 밖 main 추격 안 함;
   soft-patch 재치환 없이 가드 테스트 통과.
2) 말 턴에 MCP stdio+:8765 왕복 없음(로그/프로세스); 스킬 rg -i hermes(사용자 문구)=0.
3) settings UI 트리/소스에 Hermes API URL|Key|명령 위젯·라벨 문자열 없음(NOTICE 제외);
   .venv\Scripts\python.exe -m iris.ui._check_hermes_required 등 기존 계약은
   “Hermes 끄기 금지”가 “에이전트 필수”로 의미 유지되도록 테스트 문구 갱신.
4) 클린 홈에서 채팅·도구·위키; 구 hermes 홈 미사용.
§10.1: 툴 registry 포크 소유; 설정 생성권 Iris; 대화 정본 하나; supervisor 하나.

Work order for the implementing agent:
- Feature playbook. throughput checkpoint 작성.
- 첫 커밋 단위 = 1단계만 끝까지(검증 포함). 그다음 새 단위로 2.
- 막히면 추측으로 2/3 건너뛰지 말고 보고서 §10에 맞게 질문/결정 기록.
- 한국어로 진행 요약. 완료 시 §10.1 체크리스트 상태를 표로 보고.
```

## 새 채팅에서 붙일 한 줄

`@docs/prompts/Iris-Agent-Hermes전면흡수-일체화-구현프롬프트.md @docs/code-review/Iris-Agent-Hermes기반-구현경로.md /poteto-mode Feature: 프롬프트 순서대로 1단계부터 구현·검증.`
