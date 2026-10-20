# Prompt: 채팅 code plot (P2)

기준: `docs/code-review/채팅-GPT식표현-구현설계.md` 5.4 P2.

```text
Context:
- P0 ```matrix 렌더, P1 grid_extract 가 있다.
- GPT「분석 중」플롯은 Code Interpreter → matplotlib PNG → 채팅 첨부다.
- project.run 은 IDE 터미널용이라 채팅 PNG 회수 계약이 없다.
- matplotlib 은 .venv 에 설치한다.

Goal:
1) iris_invoke action=`chat.exec_python` args=`{code}`
   - UI 스레드 밖 실행 (control_surface _OFF_UI_ACTIONS)
   - import 화이트리스트: numpy, matplotlib, matplotlib.pyplot, PIL (필요 최소)
   - 네트워크/임의 경로 쓰기 금지. 산출 PNG 만 ~/.iris-light/runtime/plots/
   - 타임아웃(기본 20s)
   - 반환: ok_result with stdout, png_paths[], chat_markdown (이미지 MD 포함)
2) png_paths 의 로컬 경로가 채팅 Markdown 이미지로 렌더되게
   (iris-image: 또는 허용된 절대경로 src)
3) Hermes nudge 에 격자 플롯이 필요하면 chat.exec_python 쓰라는 한 줄
4) 자검: 코드로 5×5 imshow 저장 → png 존재 → chat_markdown 에 경로
   → render_iris_message 가 img 를 남긴다

Constraints:
- RestrictedPython 금지 (보안 경계 아님)
- E2B 등 클라우드 샌드박스 금지
- project.run 에 얹지 말 것
- WebEngine 채팅 교체 금지

Interface:
- iris/runtime/chat_code_exec.py
  run_chat_python(code: str, *, timeout_s: float = 20) -> dict
  keys: ok, stdout, stderr, png_paths, error
- control_actions/chat.py 등록 chat.exec_python
- plots 디렉터리: Path.home()/".iris-light"/"runtime"/"plots"

TDD:
1) iris/runtime/_check_chat_code_exec.py RED
2) 구현 후 GREEN

검증:
.venv\Scripts\python.exe -m iris.runtime._check_chat_code_exec
.venv\Scripts\python.exe -m iris.knowledge._check_grid_extract
```
