# Prompt: 채팅 GPT식 표현 — 실전 답변 계약·추출 안정화 (P3)

기준:
- `docs/code-review/채팅-GPT식표현-구현설계.md`
- 실측: Iris 컨볼루션 답(DB id 636–639)은 도구·` ```matrix ` 를 거의 안 씀.
  P1 추출은 실전 PNG에서 grid2…grid7 잡음. GPT 교재형 도식과 체감 격차.

```text
Context:
- P0: ```matrix → 색 표 렌더 (chat_renderer) 동작.
- P1: extract_binary_grid + _ocr_image 구조화 주입 동작. 픽스처는 GREEN.
  실전 스크린샷(빨간 박스·여러 패널)은 잡음 격자가 많아 모델이 틀린 층(풀링 등)을 지어냄.
- P2: chat.exec_python → plots PNG + chat_markdown 동작. 실제 Hermes 답이 호출하지 않음.
- Hermes MEMORY nudge(v23)만으로는 모델이 matrix/플롯을 쓰지 않음.
- WebEngine 채팅 전면 교체, HTML 작성 기본화는 비범위.

Goal (이번 프롬프트 구현 범위):

A) 답변 계약 (체감 1순위)
1) 격자·모폴로지·컨볼루션·이진 영상 문제에서:
   - 모델/후처리 결과 본문에 0/1 격자는 반드시 fenced ```matrix 로 나가게 한다.
   - 일반 ``` 또는 MD 표만 있는 0/1 블록은 ```matrix 로 승격하는
     display-only 정규화(답 DB 원문을 영구 훼손하지 않는 경로 우선:
     렌더 직전 normalize, 또는 저장 전 한 번).
2) 개념 도식/히트맵이 필요한 턴:
   - chat.exec_python 호출을 유도하고, 도구 결과의 chat_markdown 이미지 링크를
     최종 Iris 말풍선에 포함되게 한다.
   - 호출 실패 시 텍스트만으로 끝내되, “그림을 그리지 못함”을 거짓으로 말하지 않는다.
3) Hermes nudge를 v24로 올리고, 위 계약을 구체 예시(잘못된 출력/올바른 출력)와 함께 적는다.
   nudge만으로 부족하면 렌더 전 normalize + (선택) 도구 결과 병합 훅을 코드로 둔다.

B) P1 추출 안정화
4) extract_binary_grid 신뢰도:
   - grids 개수·크기·교차(십자 커널) 휴리스틱으로 score.
   - score 낮거나 grids > 3 이면 None 반환 → 기존 비전/OCR 경로.
   - 잡음 grid2… 를 모델에 넣지 않는다.
5) 자검: 기존 morphology 픽스처는 GREEN 유지.
   실전 컨볼루션 paste(또는 저장해 둔 fixture 복사본)에서는
   “잡음 다수 grids를 그대로 내지 않는다”를 assert
   (None 이거나 image+kernel 수준으로 정리).

C) 검증·데모
6) TDD: RED → GREEN.
   - 렌더 normalize: 일반 0/1 fence → matrix 색 표.
   - extract 신뢰도: 잡음 PNG 정책.
   - (가능하면) chat.exec_python 결과가 메시지 HTML에 img 로 남는 기존 자검 유지.
7) 데모/_check 문서 한 줄: 실전 확인 질문 예시.

Constraints:
- QTextEdit/WebEngine 전면 교체 금지.
- DALL·E/이미지 생성으로 격자 그리지 말 것.
- project.run 에 플롯을 얹지 말 것.
- RestrictedPython/E2B 금지.
- main_window Hermes 첨부 대수술 금지. 필요 시 attachment_context / renderer /
  hermes_memory_nudge / chat.exec_python 결과 병합만.
- 새 의존성 금지 (matplotlib 이미 설치됨).

Interface / data shape (권장):
- GridExtractVerdict: { ok: bool, score: float, data: dict | None, reason: str }
- normalize_binary_fences_for_display(md: str) -> str
  (0/1 only fenced blocks → language matrix; 이미 matrix면 유지)
- maybe_attach_plot_markdown(assistant_text, tool_payload) -> str
- hermes_memory_nudge marker v24 + chat.exec_python + ```matrix 계약 예시

TDD 순서:
1) 자검/테스트 RED (normalize, extract verdict).
2) 구현.
3) GREEN + P0/P1/P2 기존 자검 회귀.

검증 명령:
.venv\Scripts\python.exe -c "… normalize → render_iris_message 에 one_bg …"
.venv\Scripts\python.exe -m iris.knowledge._check_grid_extract
.venv\Scripts\python.exe -m iris.runtime._check_chat_code_exec
# 추가 모듈이 있으면:
.venv\Scripts\python.exe -m iris.ui.chat._check_gpt_answer_contract
# 또는 동등한 unittest / _check_*

완료 기준:
1) 모델이 일반 ``` 로 0/1 격자를 내도 채팅에 파란 matrix 표가 보인다.
2) 실전 컨볼루션 paste에서 STRUCTURED BINARY GRID 에 grid2… 잡음이 쏟아지지 않는다.
3) chat.exec_python 이 성공한 턴의 답에 plot img(또는 chat_markdown)가 남는다
   (도구를 쓴 경로 자검 또는 통합 스모크).
4) nudge v24에 잘못된 예/올바른 예가 있다.

비범위 (다음 단계 후보로만 적고 구현하지 않음):
- GPT급 “계산 카드” HTML/위젯.
- 자동 교재 템플릿(이동·회전 화살표 도식 전용).
- CR-IMG Hermes 첨부 스킵 전면 수정.
- WebEngine 채팅(C단계).
```

## 구현 후 수동 확인 (동일 A/B)

Iris와 GPT에 **같은 첨부·같은 문장**으로:

```
왜 이렇게 되는건지 설명해줘
(+ 컨볼루션 문제 PNG 첨부)
```

기대(Iris):
- 격자는 색 칠한 matrix 표
- (가능하면) 슬라이딩 윈도우/결과 히트맵 PNG
- 잡음 gridN 나열로 틀린 층 설명하지 않음
