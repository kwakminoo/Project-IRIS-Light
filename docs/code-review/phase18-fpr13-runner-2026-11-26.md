# Phase 18 — 13+FPR 시나리오 러너

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE18-FPR13-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | FGC · FPR-14 · R-RUNNER-FIG19 · R-13FPR-GUI |
| 대상 | 기존 `_check_*` / verify-iris 묶음 최소 러너 |
| 목적 | 계약 오프라인 전수 + 라이브 채움표 산출 |

## 1. 결론

새 테스트 프레임워크 없이 `iris.system._check_fpr13_runner`가 FGC 3a 계약 13개 + FPR 계약 3개 + 라이브 4행을 묶는다. 계약 실패 시 exit ≠ 0. 라이브는 `IRIS_FPR13_LIVE=1` / `--include-live` 없으면 skip. 결과는 `.tmp/fpr13/results.json` · `results.md`.

## 2. 구조

```text
python -m iris.system._check_fpr13_runner
  → SCENARIOS 테이블
       contract → subprocess: .venv python -m iris…_check_*
       live     → skip | 동일 subprocess
  → .tmp/fpr13/logs/<id>.log
  → results.json + results.md (채움 가능 표)
```

## 3. 코드 리뷰

| 지점 | 한 일 | 막지 못한 일 |
|---|---|---|
| `_check_fpr13_runner` | 기존 모듈 argv만 위임, JSON/MD 표 | 라이브 모델 13전수 자체 구현 |
| 기존 `_check_*` | 손대지 않음 | — |
| verify-iris | live doctor 경로만 참조 | prove_feature 전 기능 맵 미통합 |

## 4. 개선안

| 빈 자리 | 다음 |
|---|---|
| 라이브 명령 | 격리 profile + Reference 동일 조건 스크립트로 교체 |
| 표 채움 | 라이브 통과 후 results.md notes 열에 증거 경로 |

## 5. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| verify-iris `prove_feature.py` | feature→argv + evidence dir 패턴 | FPR13 표·live skip 계약이 달라 얇은 전용 러너만 |
| 찾지 못함 | FGC 전용 13-scenario 패키지 | FGC 보고서와 동일 |

## 6. 조치

1. 계약만: `.venv\Scripts\python.exe -m iris.system._check_fpr13_runner --contracts-only`
2. 라이브: `IRIS_FPR13_LIVE=1` 후 동일 모듈 (기존 홈 비터치·격리 profile 권장)
3. 커밋·push 없음

## 7. 검증 (measured)

`--contracts-only` → **exit 0**. summary: pass=16 fail=0 skipped=4 (live). 증거: `.tmp/fpr13/results.json`.
