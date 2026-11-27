# FRC-05 progress (2026-11-27)

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FRC05-PROGRESS |
| 작성일 | 2026-11-27 |
| 관련 | FRC-05 · Wave 1.7 FINAL RESIDUAL · [문서 계약](wave17-fc-document-intelligence-contract.md) |
| 대상 | Document intelligence · PDF page range · OCR · attachment_id |
| 목적 | 한 최소 검증 단위만 닫고 잔여를 분리 |

## 1. 결론

이번 단위는 **파일명/attachment_id 혼동 계약**만 닫았다. 모델이 PDF 표시 이름을 `attachment_id`로 넣어도, 세션 첨부 중 유일하면 정규 id로 해석한다. 같은 이름이 둘 이상이면 `ambiguous`와 후보 id를 돌려 재시도하게 한다. 공용 추출 캐시·OCR 취소 자검·201쪽 실모델은 잔여다.

## 2. 인벤토리 (이미 있던 것)

| 부품 | 역할 | FRC-05와의 거리 |
|---|---|---|
| `content_extract` + `read_pdf_pages` | 1-based 범위, page_status, OCR/hybrid | 범위·OCR 본선은 있음 |
| `_ocr_cancelled` / `EXTRACTION_CANCELLED` | OCR subprocess 중 취소·kill | 구현됨. 전용 자검은 없음 |
| `resolve_attachment_source` + `_check_resolve_attachment_id` | 정확 id → 경로 | 파일명 폴백·중복 거부 없음 (201쪽 FAIL 형태) |
| `AttachmentStore.roots` / `resolve_file` | 세션 첨부 인덱스·접근 재검증 | 캐시 키로 쓸 mtime·size는 인덱스에 있음. 추출 캐시 모듈 없음 |
| `_check_pdf_page_range` / `_check_chip_pdf_enrich` / `_check_ocr_fast_path` | 범위·칩·OCR 우선 | green 유지 |

선택지 중 **중복 이름/attachment_id 디스앰비규에이션**이 `resolve_*` 자검 스캐폴딩에 가장 가깝다.

## 3. 구조 (이번 요청 경로)

```
content.extract(attachment_id=?)
  → _checked_content_source (대화·워크스페이스 접근 확인)
  → resolve_attachment_source
  → AttachmentStore.canonicalize_attachment_ref   ← 이번 갈래
        exact id | unique basename | ambiguous | not found
  → resolve_file → extract_from_source(page_from/to, ocr…)
```

## 4. 코드 리뷰 (건드린 지점)

| 지점 | 이번 증상에서 한 일 | 막지 못한/안 한 일 |
|---|---|---|
| `AttachmentStore.canonicalize_attachment_ref` | 정확 id 우선, 파일 루트 basename 유일 매칭, 중복 시 ambiguous | 폴더 첨부 내부 상대경로 이름 매칭 없음 |
| `AttachmentStore.resolve_file` | resolve 전 canonicalize | 추출 결과 캐시 없음 |
| `resolve_attachment_source` | 계약 주석만 (동작은 store로 위임) | 응답 payload에 정규 id 재기입 없음 |
| `content_extract` OCR 경로 | 하지 않음 | 재OCR·취소 자검 잔여 |

## 5. 이번에 닫은 것

| 항목 | 내용 |
|---|---|
| 데이터 형태 | ref → canonical `attachment_id` (유일 basename 허용) |
| 계약 | 중복 basename → `attachment_id ambiguous; use one of: id:name, …` |
| 파일 | `iris/runtime/attachment_store.py` · `iris/ui/control_actions/wiki.py` · `iris/ui/_check_pdf_page_range.py` |
| 검증 | `python -m iris.ui._check_pdf_page_range` OK · `_check_ocr_fast_path` OK · `_check_chip_pdf_enrich` OK |

## 6. 개선안 (구조상 빈 자리만)

1. 접근 확인 후 공용 추출 캐시 (path + mtime/size + page window + ocr_language)
2. cancel-during-OCR 전용 자검 (`EXTRACTION_CANCELLED` + subprocess kill)
3. 성공 응답에 canonicalize된 `attachment_id` echo (모델 재학습 힌트)
4. 201쪽 실모델 deep-read 재측정 (값비싼 턴 — 다음 단위)

## 7. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| 로컬 의미 캐시 / RAG 인덱서 | 페이지 임베딩·재검색 | 계약이 “추출 결과 캐시”와 접근 재검증에 한정. 오버킬 |
| Tesseract 결과 디스크 캐시 라이브러리 | PNG 해시 → 텍스트 | 세션 첨부 mtime 키면 충분. 의존성 추가 불필요 |
| 찾지 못함 | OCR 취소 전용 오픈소스 하네스 | 기존 ContextVar + Popen kill로 충분 |

## 8. 조치

1. 자검 green 유지.
2. 다음 최소 단위는 추출 캐시 또는 OCR 취소 자검 중 스캐폴딩이 가까운 쪽.
3. 커밋·push·201쪽 실모델 턴은 하지 않음.
