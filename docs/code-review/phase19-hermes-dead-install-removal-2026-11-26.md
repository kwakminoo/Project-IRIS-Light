# Phase 19 — Hermes dead external-install removal

| 항목 | 내용 |
|---|---|
| 문서 번호 | phase19-hermes-dead-install-removal |
| 작성일 | 2026-11-26 |
| 관련 | class C audit (dead Hermes install path) |
| 대상 | `setup_protocol.py`, `iris_agent_install.py`, branding/owned/residue checks |
| 목적 | 제품 호출자 0인 외부 설치 잔여 삭제 |

## 1. 결론

공식 Hermes `install.ps1` 경로와 pin-checkout 헬퍼를 제거했다. 기본 설치는 vendor materialize만 남는다. class E fallback·`legacy_migration_approved`·live `~/.iris-light`는 미변경.

## 2. DeadInstallSurface

```text
DeadInstallSurface removed: {
  symbols_removed: [
    "HERMES_INSTALL_URL",
    "_run_hermes_official_installer",
    "_HERMES_IDLE_SEC",
    "_HERMES_HARD_SEC",
    "HERMES_REPO_HTTPS",
    "_checkout_pinned_sha",
    "load_upstream_url import (install module only)"
  ],
  checks_updated: [
    "iris/ui/_check_hermes_user_branding_p4.py",
    "iris/system/_check_iris_agent_owned_install.py",
    "iris/system/_check_iris_agent_product_residue.py"
  ],
  verification: {
    "_check_iris_agent_owned_install": 0,
    "_check_iris_agent_product_residue": 0,
    "_check_hermes_user_branding_p4": 1
  }
}
```

## 3. 구조

```text
SetupProtocol.iris_agent_install
  └─ (was) _run_hermes_official_installer + HERMES_INSTALL_URL  → REMOVED
  └─ owned path: iris_agent_install.install_* → _materialize_owned_core

iris_agent_install
  └─ (was) _checkout_pinned_sha + HERMES_REPO_HTTPS  → REMOVED
  └─ default body already materialize-only
```

## 4. 코드 리뷰

| 지점 | 이번 일 | 비고 |
|---|---|---|
| `HERMES_INSTALL_URL` / `_run_hermes_official_installer` | 삭제 | Grep 상 제품 호출자 0 |
| `_checkout_pinned_sha` / `HERMES_REPO_HTTPS` | 삭제 | 기본 install body 미사용 |
| branding_p4 | 「상수 존재」→「부재」assert | dead-install 구간은 통과 |
| owned_install | 모듈 전체에서 심볼 부재 요구 | exit 0 |
| product_residue | allowlist에서 `HERMES_INSTALL_URL` 제거 | exit 0 |

## 5. 확인

| 체크 | exit |
|---|---|
| `python -m iris.system._check_iris_agent_owned_install` | 0 |
| `python -m iris.system._check_iris_agent_product_residue` | 0 |
| `python -m iris.ui._check_hermes_user_branding_p4` | 1 |

branding_p4 실패는 `setup_logos.py`에 `'"hermes": "IA"'` 없음(line ~122). 이번 삭제와 무관한 기존/병렬 Gate B 잔여. dead-install assert(HERMES_INSTALL_URL / `_run_hermes_official_installer` / install.ps1 부재)는 같은 실행에서 통과.

## 6. Leftover callers

iris/ 내 제품 코드: 없음. 체크 파일의 「부재 assert」문자열만 남음. `.audit/` 스냅샷은 미수정.

## 7. 조치

1. 완료 — class C dead install 삭제 + 체크 뒤집기.
2. branding_p4 logos `"hermes": "IA"` — Gate B/병렬 작업에 위임.
3. class E `iris_agent_repo_dir` hermes fallback — 이번 범위 밖.
