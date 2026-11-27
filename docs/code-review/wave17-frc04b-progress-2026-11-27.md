# FRC-04B 진행 (2026-11-27)

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FRC-04B-2026-11-27 |
| 작성일 | 2026-11-27 |
| 관련 | WAVE 1.7 FINAL RESIDUAL CLOSURE · FRC-04B |
| 대상 | Host MCP 바인딩 신뢰 재검증 (승인 직후 스키마 지문) |
| 목적 | 가장 작은 검증 단위 하나 닫기 |

## 1. 결론

승인 직후에도 Host는 바인딩에 고정된 `schema_fingerprint`를 `_run_sdk` 요청에 실어 보내고, 라이브 스키마 불일치(`schema_changed`)면 도구를 성공으로 취급하지 않는다. FRC-04A(서명 Webhook)는 손대지 않았다.

## 2. 이번 단위

| 항목 | 내용 |
|---|---|
| 선택 | 승인 대기·승인 직후 스키마 지문 거부 (기존 `invoke_binding` / `_run_sdk` 스캐폴딩) |
| 미선택 | stdio kill 재연결, 이중 서버 discovery isolation (다음 단위) |
| 제품 코드 | 변경 없음 — 거부 경로는 이미 `NativeMCPManager.invoke_binding` → `call_tool` → `_operate` |
| 검증 | `python -m iris.mcp._check_schema_refuse_after_approval` (pytest 래퍼: `test_schema_fingerprint_refused_after_approval`) |

## 3. 구조

```
invoke_binding(binding, args)
  → human approve
  → _binding_status (config fingerprint)
  → call_tool(..., expected_schema=binding.input_schema)
       → _run_sdk request.schema_fingerprint
            → (live mismatch) status=schema_changed
  → ok=False, error_code=schema_changed
```

기존 인접 커버: `test_model_bindings_are_scoped_and_approval_cannot_outlive_config` (승인 중 config disable → `disabled` / 재활성 → `config_changed`). 이번 단위는 config가 아니라 **스키마 지문** 축이다.

## 4. 조치

1. `python -m iris.mcp._check_schema_refuse_after_approval` → `ok: schema fingerprint refused after approval`.
2. 다음 FRC-04B 단위 후보: dual-server discovery isolation 또는 stdio kill 후 reconnect.
3. 전체 완료 기준(다중 서버 실검색 · 거부·취소·재시작·단절 조합 · 실모델 MCP)은 아직 열림.
