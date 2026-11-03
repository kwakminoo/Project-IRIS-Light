# Prompt: 채팅 격자 Vision 구조화 (P1)

기준: `docs/code-review/채팅-GPT식표현-구현설계.md` 5.3 P1.

```text
Context:
- 이미지 첨부는 attachment_context._ocr_image → 비전 reader 또는 Tesseract OCR 이다.
- OCR은 5×5·커널 위상을 자주 깨뜨린다. 모델에 잘못된 0배열이 간다.
- P0 로 ```matrix 렌더는 있다. 모델 입력에 올바른 격자 JSON/matrix 가 있어야 답이 산다.
- P2 code plot, WebEngine, HTML 작성 기본은 범위 밖.

Goal:
1) extract_binary_grid(path) → dict | None
   - grids: [{name, data: list[list[int]]}]  (0/1)
   - 모폴로지 픽스처에서 name image = 5×5 중앙 3×3 전경, name kernel = 3×3 십자
2) 추출 성공 시 _ocr_image 가 OCR 대신 STRUCTURED BINARY GRID 텍스트
   (안에 ```matrix 블록 포함) 을 반환한다.
3) 실패 시 기존 비전/OCR 경로를 그대로 탄다.
4) 자검: 픽스처 PNG → extract + prepare/ _ocr 경로가 커널·전경을 재현.

Constraints:
- 새 클라우드 VLM API 의무화 금지. PIL(+numpy/cv2 이미 있음)로 셀 격자 추출.
- main_window Hermes 분기 대수술 금지. _ocr_image / prepare_attachments 경로에 꽂는다.
- diagram_card, chat_renderer matrix 렌더 계약은 유지.

Interface / data shape:
- BinaryGridSet: TypedDict 또는 dataclass
  grids: list[{name: str, data: list[list[int]]}]
  op_hint: str | None
- iris/knowledge/grid_extract.py
  extract_binary_grid(path) -> dict | None
  format_grid_attachment_text(data) -> str
  write_morphology_fixture(path) -> None  (자검용, 테스트에서만 써도 됨)
- attachment_context._ocr_image: extract 성공 시 format 텍스트 반환

TDD:
1) tests/test_grid_extract.py (또는 iris/knowledge/_check_grid_extract.py) RED
2) 구현 후 GREEN

검증:
.venv\Scripts\python.exe -m iris.knowledge._check_grid_extract
.venv\Scripts\python.exe -c "… matrix fence 회귀 …"

완료 기준:
- 픽스처에서 image data 중앙 3×3 이 1, kernel 이 십자(중심+상하좌우 1).
```
