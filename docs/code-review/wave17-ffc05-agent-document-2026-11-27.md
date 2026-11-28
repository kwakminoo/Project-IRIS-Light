# FFC-05 Agent & Document Reliability

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FFC05-AGENT-DOCUMENT |
| 작성일 | 2026-11-27 |
| 관련 | [05 프롬프트](../prompts/) · [04 인수인계](wave17-ffc05-handoff-from-ffc04-2026-11-27.md) · [문서 계약](wave17-fc-document-intelligence-contract.md) |
| 대상 | Agent 복구 계약 · 첨부 canonicalize · 추출 캐시 · 201p L2 · OCR 취소 |
| 목적 | 제품 지원 환경 L2/L3 수용 기준과 잔여(UNVERIFIED)를 고정한다 |

## 1. 결론

FFC-05의 코드 계약은 L2에서 닫혔다. 추출 캐시는 세션 `AttachmentStore`에 묶인 memo다. OCR 취소와 canonical `attachment_id` echo, 201쪽 페이지 창 추출, Agent `RecoveryClass` 진단·uncertain 재시도 금지가 자검으로 통과했다. 실모델 10회 안정성·201p L4·mixed 순서 단언은 UNVERIFIED로 06에 넘긴다.

## 2. 확인한 사실

| 자검 | 결과 |
|---|---|
| `python -m iris.knowledge._check_extraction_cache` | ok |
| `python -m iris.knowledge._check_ocr_cancel` | ok |
| `python -m iris.ui._check_pdf_page_range` | ok (canonicalize echo 포함) |
| `python -m iris.ui._check_ffc05_pdf_201p` | ok (L4 UNVERIFIED) |
| `python -m iris.runtime._check_ocr_fast_path` | ok |
| `python -m iris.ui._check_chip_pdf_enrich` | ok |
| `python -m iris.system._check_ffc05_agent_recovery` | ok |
| `python -m iris.mcp._check_multiserver_reconnect` | ok (Unit D 재확인) |

캐시 arena base는 Candidate B. A의 vision 활성 시 캐시 금지만 graft. 근거: `docs/code-review/_arena-ffc05-cache/SYNTHESIS.md`.

## 3. 구조

```
Agent 경로
  tool result / error
    → iris.system.agent_recovery.diagnose_recovery
    → should_auto_retry (execution_uncertain + side-effect → False)
    → recover_path_arg (명시 스코프만)

Document 경로
  content.extract(args)
    → _checked_content_source / resolve_attachment_source
    → AttachmentStore.canonicalize_attachment_ref
    → extract_from_source(..., memo=memo_for_store(store))
         ├─ pdf|image: ExtractionMemo get/put (vision·error 제외)
         └─ read_pdf_pages leaf (캐시 없음)
    → success payload.attachment_id = canonical id
```

이번 요청 갈래: `extract_from_source` wrap · `wiki.content_extract` memo/echo · `agent_recovery` 신규.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 막지 못한 / 하지 않은 일 |
|---|---|---|
| `extraction_cache.py` | store-bound LRU+TEMP spill, size+mtime+window+OCR key | 프로세스 넘어 영속 캐시 없음 |
| `content_extract.extract_from_source` | pdf\|image hit/miss, vision skip, error 미적재 | `read_pdf_pages` 직접 호출은 캐시 없음 |
| `attachment_store` | clear/detach/index drift invalidate | 폴더 첨부 상대경로 이름 매칭 없음 (기존) |
| `wiki.content_extract` | memo 전달 + canonical id echo | vision.analyze_attachment echo는 원본 id 유지 |
| `_ffc05_pdf_fixture` + `_check_ffc05_pdf_201p` | 201p L2 창 추출 | 실모델 L4 없음 |
| `agent_recovery` | RecoveryClass 표, uncertain 재시도 금지, 경로 스코프 | Native/MCP/mixed 각 10회 실모델 없음 |

## 5. 개선안 (빈 자리만)

1. 제품 프로필에서 Native file · MCP · mixed 각 10회 fixture 기록 (미달 시 UNVERIFIED).
2. 201p 실모델 L4 (페이지 87/201 marker grounding).
3. mixed 실행 순서 단언이 과업에 본질적일 때만 순서 검사 추가.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| `~/.iris-light` 영속 disk blob (arena A) | 프로세스 간 재사용 | 세션 revoke·orphan 위험. B가 접근 수명과 맞음 |
| 페이지 임베딩 RAG | 의미 검색 | 계약이 추출 결과 캐시·접근 재검증에 한정 |
| 찾지 못함 | OCR 취소 전용 외부 하네스 | 기존 ContextVar + Popen kill로 충분 |

## 7. 조치

1. L2 자검 green 유지.
2. 06에 UNVERIFIED 실모델·10회 안정성·선택적 mixed 순서 전달.
3. 커밋·push는 사용자 요청 시에만.
