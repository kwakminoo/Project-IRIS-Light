# Prompt: IRIS IDE Phase 1 — 정직화 (쓰기·열기·저장 = 실측)

> **상태 (2026-10-28): 구현·자검 완료.** 보관용. 다음 = 단계표 2단계(공간 동기) 프롬프트 요청 후 새 채팅.

기준 문서:

- `docs/code-review/Iris-IDE-커서조작-일체화-단계표.md` §5.1
- `docs/code-review/IDE-커서처럼-조작-현황.md` §6~§8 (특히 visible / bridge_fallback / save)

다음 단계(공간 동기·드래그·진단·셸 브랜드)는 **이 단계 완료 전 구현 금지**.

```text
Context:
- 제품 구조: Iris Agent(뇌) → IDE/project 도구 → standalone-bridge + Theia 폴러 → IRIS IDE 화면.
- 뇌는 Theia에 넣지 않는다. Companion·worktree 자동 전환·탭 드래그·LSP 깊이는 2~4단계.
- 이미 한 일(회귀 금지, 다시 “성공 위장”으로 되돌리지 말 것):
  - standalone-bridge openFile/gotoFile: bridge_fallback 없음. 타임아웃 = HTTP 오류.
  - iris_ide_editor_opened: via==bridge_fallback 또는 opened==false → 실패.
  - project.write_file (iris_ide): open 실패 시 visible:false + ok 실패 경로.
  - iris/system/_check_ide_link.py: open timeout / legacy bridge_fallback 거절 assert.
- 아직 애매한 곳(이번 단계에서 닫을 것):
  - saveFile: 폴러 없을 때 { saved:true, via:'disk', editor:false } — 에이전트/호출부가
    “편집기에 저장됨”과 구분하지 못하면 가짜 완료.
  - integrations/iris-ide/src/node/iris-ide-bridge-server.ts 등 비-폴러 경로가
    opened:true 를 낼 수 있으면 제거 또는 실측만.
  - 사용자/도구 오류 문자열에 “Theia”가 남아 IRIS IDE 일체화와 어긋남(NOTICE 제외).
  - 설치본 bundle ↔ 소스 불일치 시 정직화 코드가 실행에 안 탐.

Goal (이 채팅에서 1단계만 끝까지):

1) 감사(Audit)
   - openFile / gotoFile / createFile+open / project.write_file / ide.open_file /
     saveFile·saveAll 경로에서 “성공인데 화면·버퍼와 무관”한 반환을 표로 나열.
   - bridge_fallback 문자열·분기가 소스·번들에 재도입되지 않았는지 rg.

2) 계약 고정
   - 열기: 폴러가 opened:true(및 허용 viewer)일 때만 visible/ok.
   - 저장: 편집기 저장 성공과 디스크-only를 필드·오류로 구분.
     디스크-only를 기본 “저장 성공(편집기)”로 취급 금지.
     호출부가 editor:false / via:disk 를 ok처럼 말하게 두면 고친다(실패 또는 명시 플래그).
   - 비-폴러 서버가 opened:true 단독 반환하면 폴러 대기 또는 오류로 통일.

3) 자검
   - 기존 _check_ide_link / _check_iris_ide_bridge_nav 유지·보강.
   - save 구분(디스크 vs 편집기) assert 추가(최소 1개 모듈).
   - iris_ide_editor_opened(bridge_fallback) 거절은 유지.

4) 번들
   - TS/브리지 수정 시:
     .venv\Scripts\python.exe -c "from iris.system.iris_ide_runtime import shared_iris_ide_runtime; ok,m=shared_iris_ide_runtime().sync_workspace_build(print); assert ok, m"
   - 워크스페이스·설치본에 정직화 마커(관련 문자열) 존재 확인.

5) 제품 언어
   - 사용자/도구 노출 오류에서 Theia → IRIS IDE (라이선스·NOTICE·주석·업스트림 import 경로 제외).

6) 버그 탐색 (구현 후)
   - 폴러 죽인 채 open → 반드시 실패.
   - 정상 Companion에서 write_file → 탭 실측 + visible true.
   - save: 편집기 열린 파일 / 없는 경로 / 폴러 없음 — 결과가 계약과 일치.
   - no-console: 이 경로에서 새 Cascadia 창 없음.
   - qt-slot-abort: 새 슬롯 속성 누락 없음.

Constraints:
- 2단계(worktree↔폴더), 3단계(드래그), 4단계(진단/심볼 신규), 5단계(시작화면 브랜드 대규모) 금지.
- 에이전트 루프·@theia/ai 추가 금지.
- CREATE_NO_WINDOW / no_window_kwargs / iris-ide-rebuild-sync / thin IRIS.exe 계약 유지.
- 커밋은 사용자 요청 있을 때만.
- ponytail: 최소 변경. 감사에서 “이미 닫힘”이면 테스트만 보강하고 코드를 건드리지 않음.
- 인라인 import 금지(프로젝트 규칙).

Interface / 손댈 후보:
- integrations/iris-ide/bridge/standalone-bridge.js (save 계약)
- integrations/iris-ide/src/node/iris-ide-bridge-server.ts (열린 척 반환)
- integrations/iris-ide/src/browser/iris-ide-bridge-poller.ts / bridge-ops.ts (필요 시)
- iris/ui/control_bindings.py (iris_ide_editor_opened)
- iris/ui/control_actions/project.py (write_file visible)
- iris/system/ide_link.py / IrisIdeClient
- iris/system/_check_ide_link.py 및 save용 체크 보강
- 스킬 문구는 “열기 실패=실패”만 맞으면 최소 수정(대규모 스킬 개편은 4단계)

검증 (모두 통과해야 1단계 완료):
A) rg bridge_fallback integrations/iris-ide iris --glob '!**/completed/**' → 거절/주석/테스트 외 “성공 반환” 분기 0
B) .venv\Scripts\python.exe -m iris.system._check_ide_link
C) save 구분 자검(신규 또는 확장) 통과
D) IDE 소스 만졌으면 sync_workspace_build 성공 + 설치본 반영
E) 수동 또는 기존:
   .venv\Scripts\python.exe -m iris.ui._check_iris_ide_window
   (해당되면) _check_iris_ide_bridge_nav / _check_ide_request_tools
F) 완료 보고 표:
   | 경로 | 이전 | 이후 | 자검 |
   open / write visible / save editor vs disk / Theia 문자열

Work order for the implementing agent:
1. Feature playbook. throughput checkpoint.
2. Audit 표 먼저 → Goal 2 계약만 코드.
3. 자검 → sync(필요 시) → 버그 탐색.
4. 한국어로 짧게: 구조(무엇이 정직해졌는지) → 증거(명령·결과).
5. 1단계 완료라고 말하려면 위 A~F. 미완이면 “다음 채팅에서 이어서” + 남은 칸.
6. 완료 시 archive: 이 프롬프트를 docs/prompts/completed/ 로 git mv(사용자 요청·확인 후).
   단계표 §5.1에 완료일·증거 한 줄 갱신. 2단계 프롬프트는 작성하지 말고
   사용자에게 “문서 채팅에서 Phase2 프롬프트 요청”만 안내.
```

## 새 채팅에서 붙일 한 줄

```text
docs/prompts/Iris-IDE-Phase1-정직화-구현프롬프트.md 대로 IRIS IDE Phase1 정직화만 구현·자검·버그탐색해줘. 2~5단계·에이전트 뇌 Theia 흡수는 하지 마.
```
