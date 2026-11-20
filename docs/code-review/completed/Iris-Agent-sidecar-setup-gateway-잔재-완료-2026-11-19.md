# Iris Agent setup·gateway 잔재 정리 완료

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-19-SIDECAR-SETUP |
| 작성일 | 2026-11-19 |
| 관련 | Unit0–3, InternalSidecar-only |
| 목적 | 제품 설치·진단이 sidecar 의미와 일치함을 고정 |

## 1. 결론

제품 readiness는 InternalSidecar 턴 import·SpeakTools 자세다. `:8642` start/ensure/restart는 stub. 레거시 `IRIS_HERMES_BASE_URL=:8642`는 채팅 URL을 비운다. 툴 카탈로그는 미변경.

## 2. 확인한 사실

| 사실 | 근거 |
|---|---|
| Unit0 Delete(gut) | `docs/code-review/completed/…Unit0-결정.md` |
| probe = sidecar | `probe_agent_runtime` · `_check_agent_runtime_probe_sidecar` |
| lifecycle stub | `_check_no_product_gateway_ops` |
| legacy URL 무시 | `load_settings` → `agent_base_url==''` |
| setup summary | `Iris Agent sidecar ready · SpeakTools…` (8642 없음) |
| chat landing | `_check_chat_landing_contract` ok |
| branding labels | `_check_iris_agent_branding` unit3 ok |

## 3. 구조

```
setup agent_runtime
  → probe_agent_runtime (sidecar imports)
  → ensure_iris_agent_runtime(start_gateway=False)
  → verify_iris_mcp_tools / SpeakTools
  ✗ start/ensure/restart :8642 (stub)
```

## 4. 조치

1. 구현 프롬프트·Unit0 결정은 `docs/**/completed/`로 이동.
2. 커밋/PR은 사용자 요청 시.
