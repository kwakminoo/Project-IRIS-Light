# Prompt: P5 InternalSidecar UTF-8 파이프 — 한글 깨짐

새 Cursor 채팅에 아래 블록만 붙여 넣는다.

```text
Context:
- /poteto-mode Bug fix
- 저장소: Project-IRIS-Light (Windows)
- 증상: 채팅 답이 `ȳϼ…` / U+FFFD 대량. Iris DB 사용자 메시지는 UTF-8 정상.
- 원인 (측정됨): 기본 경로 InternalSidecar. 부모는 stdin/stdout을 encoding=utf-8, errors=replace 로 연다.
  `_sidecar_env`에 PYTHONUTF8/PYTHONIOENCODING이 없다. 자식(엔진 venv python)이 Windows에서
  sys.stdin/out=cp949가 되면 UTF-8 NDJSON 한글이 깨지고, 부모가 utf-8+replace로 읽어 FFFD가 된다.
  ExternalGateway(HTTP)는 한글 정상. MCP iris-control env에는 이미 PYTHONUTF8=1 있음.
- 재현: stripped env에서 PYTHONUTF8 제거 후 엔진 python으로 NDJSON 한글 round-trip → hangul False.
- 핵심 파일: iris/engine/runtime.py (_sidecar_env, _spawn_sidecar), iris/engine/_sidecar_main.py
  관련: iris/engine/_home.py (_stripped_probe_env)

Goal:
1) sidecar 자식 프로세스에 UTF-8을 강제한다 (PYTHONUTF8=1, PYTHONIOENCODING=utf-8).
2) 가능하면 sidecar_main 기동 직후 stdin/stdout을 utf-8로 reconfigure (방어).
3) 자검: PYTHONUTF8 없는 env에서도 한글 NDJSON round-trip이 깨지지 않음 (assert).
4) 기존 engine/sidecar 테스트·자검이 있으면 통과. 없으면 최소 _check 추가.
5) P1–P4 / options 가드 / SOUL / MEMORY 브랜드 스윕을 되돌리지 말 것.

Constraints:
- Surgical. engine sidecar 인코딩만. ExternalGateway·모델·UI 리팩터 금지.
- 커밋/PR 금지.
- no-console-windows 유지 (no_window_kwargs 유지).
- errors=replace를 성공 경로의 데이터 손실로 남기지 말 것. 자식이 UTF-8이면 replace는 백스톱.

Verify:
- PYTHONUTF8 unset 환경에서 엔진 python + 부모 utf-8 파이프로
  messages content "안녕 이리스" → delta/응답에 "안녕" 포함.
- .venv\Scripts\python.exe -m … (추가한 _check)
- 한국어로 broken/cause/fix/verify 보고. 변경 파일 목록.

Output: 최소 diff. 프롬프트는 완료 후 docs/prompts/completed/ 로 이동.
```
