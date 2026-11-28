# FFC-06 인수인계 (from FFC-05)

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FFC06-HANDOFF-FROM-05 |
| 작성일 | 2026-11-27 |
| 기준 | FFC-05 L2 green · [상세](wave17-ffc05-agent-document-2026-11-27.md) |
| 목적 | 05에서 닫은 계약과 남은 실증을 06에 넘긴다 |

## 05가 닫은 계약

- store-bound 추출/OCR 캐시 (`extraction_cache`, vision/error 미적재, detach/drift invalidate)
- OCR mid-cancel → `EXTRACTION_CANCELLED` 자검
- `content.extract` 성공 payload의 canonical `attachment_id` echo
- 201p fixture L2 페이지 창 추출 (마커 grounding)
- `RecoveryClass` 진단 · `execution_uncertain` 부작용 자동 재시도 금지 · 경로 스코프 복구

## 05가 신뢰할 증거

- `python -m iris.knowledge._check_extraction_cache`
- `python -m iris.knowledge._check_ocr_cancel`
- `python -m iris.ui._check_pdf_page_range`
- `python -m iris.ui._check_ffc05_pdf_201p`
- `python -m iris.system._check_ffc05_agent_recovery`
- Arena synthesis: `docs/code-review/_arena-ffc05-cache/SYNTHESIS.md`

## 열려 있는 항목 (UNVERIFIED)

- Native file search/read, MCP, mixed 각 10회 독립 fixture (최초 8/10, 복구 포함 9/10, grounding 100%)
- 201p 실모델 L4 (페이지별 고유 값 반환)
- mixed 실행 순서 단언이 과업에 본질적일 때의 순서 검사
- 캐시 hit/miss latency·peak memory 실측 기록

## 06 진행 시 지킬 경계

- Desktop은 Gateway 없이 동작. Native Dispatcher/SpeakTools/Policy만 실행 정본.
- uncertain 부작용 자동 재실행 금지.
- 캐시 키에 파일명만 쓰지 말 것. 접근 재검증 유지.
- 사용자 Wiki/Memory를 파괴적 fixture로 쓰지 말 것.
