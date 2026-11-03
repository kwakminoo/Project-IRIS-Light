# Prompt: IRIS IDE Phase 5 — 셸 일체화 (작업대 제품 느낌)

기준:

- `docs/code-review/Iris-IDE-커서조작-일체화-단계표.md` §5.5
- Hermes→Iris Agent 일체화의 “이름·수명·NOTICE만 고지” 패턴
- Phase1~4 completed. 조작 계약 회귀 금지.

6단계(색인·인라인 완성)·뇌 Theia 흡수·엔진 포크 **금지**.

```text
Context:
- applicationName 은 이미 "IRIS IDE". 일상 UI·로딩·설정·오류에 “Theia”가 남아
  “붙여 넣은 엔진”처럼 보인다 (예: iris_ide_window 로딩, iris_ide_settings 문구).
- LICENSE/THIRD_PARTY_NOTICES 의 Theia·EPL 고지는 유지(숨기지 않음).
- 기동은 Iris 경로(iris_ide_runtime / Companion). 사용자 theia CLI 불필요 상태 유지·강화.
- Companion 수명·고아 창: _check_ide_companion_windows 계약.

Goal (5단계만):

1) 제품 언어 (일상 UI)
   - 사용자가 보는 문자열(로딩, 설정 안내, 토스트, 도구 오류, 시작 화면 카피)에서
     Theia → IRIS IDE (또는 “IDE”).
   - 제외: LICENSE.md, THIRD_PARTY_NOTICES.md, package.json license 필드,
     import 경로 @theia/*, 코드 식별자(theia_load_finished 등 심볼 대량 rename 금지),
     개발자 주석 중 엔진 설명은 최소 유지 가능.
   - 설정 설치 문구: “yarn · tsc · theia build” 같은 내부 파이프라인은
     “IRIS IDE 빌드”로 사용자에게 보이게. 로그 상세에 theia 가 남는 건 OK(개발용).

2) 기동·수명
   - IDE는 Iris API(shared_iris_ide_runtime / Companion)로만 연다고 문서+코드 주석 한 줄.
   - Companion 종료/복귀 시 고아 Iris Light 창 없음 — _check_ide_companion_windows 통과.
   - 창 제목/시작 화면이 IRIS IDE 인지 소스·번들 마커 확인(대규모 UI 리디자인 금지).

3) 고지
   - LICENSE §6 / THIRD_PARTY_NOTICES 에 Theia 기반이 남아 있는지 확인만.
     없으면 최소 한 절 보강. 일상 UI에 라이선스 전문을 띄우지 않음.

4) 자검
   - rg 사용자 노출 경로( iris/ui/settings/iris_ide_settings.py,
     iris/ui/workspaces/iris_ide_window.py 로딩 문자열,
     control_actions 오류 문자열)에 단독 "Theia" 사용자 카피 0
     (NOTICE/LICENSE/식별자 제외 규칙은 체크 스크립트에 명시).
   - .venv\Scripts\python.exe -m iris.ui._check_ide_companion_windows
   - .venv\Scripts\python.exe -m iris.ui._check_iris_ide_window
   - Phase1~4 핵심 회귀 최소 세트:
     _check_ide_link, _check_ide_workspace_sync, _check_iris_ide_bridge
   - TS/시작화면 카피 수정 시 sync_workspace_build.

Constraints:
- Phase6 색인·완성 금지. @theia/ai 금지.
- 심볼명 load_theia / _load_theia_after_launch 전면 rename 금지(범위 폭발).
  사용자 문자열만.
- 타일·new-window·no-console·정직화·공간동기·드래그 회귀 금지.
- 커밋 금지. 인라인 import 금지.

Interface / 손댈 후보:
- iris/ui/workspaces/iris_ide_window.py (show_loading 등)
- iris/ui/settings/iris_ide_settings.py
- integrations/iris-ide 시작 화면 카피(있으면)
- iris/ui/_check_iris_ide_branding.py (신규 권장: 사용자 문자열 Theia=0)
- docs: 단계표 §5.5만. 새 장문 보고서 금지.

검증:
A) branding/Theia 사용자 문자열 자검
B) companion windows + iris_ide_window
C) Phase1~4 최소 회귀
D) 필요 시 sync_workspace_build
E) 단계표 §5.5·요약행 완료. 프롬프트 completed/.
   “1~5 1차 완료”를 단계표 조치에 한 줄. Phase6 프롬프트 쓰지 않음.
```

## 에이전트 한 줄

```text
docs/prompts/Iris-IDE-Phase5-셸일체화-구현프롬프트.md 대로 Phase5만. Phase6·뇌 Theia 금지. 커밋 금지. 사용자 문자열 일체화에 집중.
```
