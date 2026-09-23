# 코어 스모크 묶음

| 항목 | 내용 |
|------|------|
| 목적 | 휘발성 코드 반증 — **한 커맨드**로 핵심 회귀 |
| 실행 | `powershell -ExecutionPolicy Bypass -File scripts\run_core_smoke.ps1` |
| 작성일 | 2026-09-23 |

---

## 포함 체크

| ID | 모듈 | 의도 |
|----|------|------|
| S1 | `iris.ui._check_iris_startup` | 시작·부트 경로 |
| S2 | `iris.system._check_gateway_setup_step` | Gateway / setup 단계 |
| S3 | `iris.ui._check_hermes_required` | Hermes 필수 배선 |
| S4 | `iris.ui._check_control_scenarios` | Control Surface 시나리오 |
| S5 | `iris.ui._check_iris_ide_companion_tile` | IDE 80:20 타일 계약 |

환경에 따라 일부는 스킵(의존 서비스 없음)될 수 있다. 스크립트는 **실패(non-zero)만 전체 실패**로 집계한다.

---

## 인용 (발표·문서)

- 도메인: [`docs/domain.md`](../domain.md)
- IA: [`docs/ia/IA.md`](../ia/IA.md)
- 체크 스크립트 위치: `iris/**/_check_*.py` (50+)
- 사람 검증: [`기능테스트-시나리오서.md`](기능테스트-시나리오서.md)
