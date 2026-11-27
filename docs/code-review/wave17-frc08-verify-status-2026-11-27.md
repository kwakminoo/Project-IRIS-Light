# FRC-08 / FRC-08W 검증 상태 (2026-11-27)

| 항목 | 내용 |
|---|---|
| 문서 번호 | WAVE17-FRC08-VERIFY-2026-11-27 |
| 작성일 | 2026-11-27 |
| 관련 | WAVE 1.7 FINAL RESIDUAL CLOSURE · FRC-08 · FRC-08W · [FC 인수인계](wave17-fc-validation-handoff.md) · [FRC 추적표](wave17-frc-tracker-2026-11-27.md) |
| 대상 | 격리 Core 수명주기 · Launcher/Setup 빌드 증거 · Windows 클린 OS 가용성 |
| 목적 | 공개 migration 없이 VERIFY 상태만 전진. `legacy_migration_approved`는 false 유지 |

## 1. 결론

FRC-08은 **PARTIAL**. 이 PC의 격리 `IRIS_HOME` 수명주기(`installer_lifecycle` PASS)와 Launcher/Setup 0.1.18 재빌드 증거가 이미 있고, 오늘 `--contracts-only` 재검도 17 PASS · 0 FAIL이다. FRC-08W는 **BLOCKED(가용성 제약 명시)**. 두 번째 클린 Windows OS·Hyper-V 관리 VM이 이 머신에 없다. 공개 Setup 설치·업데이트·롤백은 미실행. `legacy_migration_approved`를 true로 바꾸지 않았고 커밋·push도 없다.

## 2. 디스크에 있는 증거 (재사용)

| 증거 | 경로 | 측정 |
|---|---|---|
| FPR13 격리+수명주기 최종 | `.tmp/wave17-functional-closure/fpr13-isolated-final/results.json` | `started_at` 2026-11-27T06:13:42Z. **18 PASS · 0 FAIL · 7 UNVERIFIED**. `installer_lifecycle` **PASS** |
| 수명주기 로그 | `.tmp/wave17-functional-closure/fpr13-isolated-final/logs/installer_lifecycle.log` | `_check_owned_lifecycle` exit=0 · ~117s. 설치→HELLO→업데이트→롤백→복구. `preserved_user_data: True` |
| Launcher 빌드 | `.tmp/w17-fc-build/launcher.log` | PyInstaller Launcher 로그 (2026-11-27) |
| Setup 빌드 | `.tmp/w17-fc-build/setup-final.log` · `.tmp/w17-fc-build/dist/IRIS-Setup-0.1.18.exe` | 42,591,953바이트. SHA-256 `3B4A0D1E26C3FC406A106F0931264A1951C93CDDF6D8EECB7EF3573B960A6E71` (FC handoff와 일치) |
| FC handoff 서술 | [wave17-fc-validation-handoff.md](wave17-fc-validation-handoff.md) §실제 실행 증거 | 격리 Core 수명주기 + Launcher/Setup 행이 FRC-08 완료 기준의 상당부를 이미 담음 |
| 오늘 contracts-only 재검 | `.tmp/wave17-functional-closure/fpr13-contracts-frc08-verify/results.json` | 2026-11-27T09:33:59Z. **17 PASS · 0 FAIL · 8 UNVERIFIED**. live/gui/lifecycle/product 플래그 없음 |

`installer_lifecycle` 요약 (isolated-final 로그): 새 슬롯 `iris-agent.slot-f107c3e4fad74514` 설치 → HELLO → 후보 업데이트 `slot-e4f074badfe1437b` → 롤백 → 복구. 사용자 데이터 보존 True.

## 3. 오늘 실행한 검사

| 명령 | 파괴성 | 결과 |
|---|---|---|
| `python -m iris.system._check_fpr13_runner --contracts-only --out-dir .tmp/wave17-functional-closure/fpr13-contracts-frc08-verify` | 없음 (계약만) | exit 0. 계약 17 PASS. L3/L4/L5/L6·진단은 skip→UNVERIFIED |

의도적으로 **돌리지 않은 것**

| 플래그 | 이유 |
|---|---|
| `--include-lifecycle` | 이미 `fpr13-isolated-final`에 L6 PASS. 긴 재설치. 공개 migration 아님이나 중복 비용 |
| `--include-live` / `--include-gui` / `--product-home` | FRC-08 VERIFY 단위 밖. 제품 홈·데스크톱 GUI 의존 |
| Setup 실제 설치 | FRC-08W. 클린 OS 없음. 개발 홈 irreversibility 위험 |

## 4. FRC-08W 가용성 제약

| 항목 | 측정 |
|---|---|
| 현재 OS | Windows 11 Home · Build 26200 · x64 (단일 부팅 환경) |
| HypervisorPresent | True (VBS/하이퍼바이저 감지) |
| Hyper-V VM 목록 | `Get-VM` 없음 (관리 모듈/기능 미가용 또는 Home 제약). elevation 없이 OptionalFeature 조회 실패 |
| 두 번째 클린 Windows | **없음**. 별도 파티션·별도 PC·준비된 클린 VM 이미지 미확인 |
| 결론 | FRC-08W 완료 기준(클린 OS Setup→업데이트→롤백)은 **이 머신에서 실행 불가**. 제약을 명시하고 BLOCKED로 둔다. 해결은 별도 클린 Windows 또는 승격된 Hyper-V/외부 VM |

## 5. 상태 판정

| ID | 이전 | 이번 | 근거 |
|---|---|---|---|
| FRC-08 | OPEN | **PARTIAL** | 격리 L6 + Launcher/Setup 빌드 + contracts-only 재검. 잔여: 임시 확장 공개 경계 실측, L3/L4/L5 live·GUI 재번(선택) |
| FRC-08W | OPEN | **BLOCKED (가용성 제약)** | 두 번째 클린 Windows OS 불가. 격리 디렉터리 L6는 FRC-08 쪽 증거로만 인정 |

공개 릴리스·Wave 2는 계속 **NO-GO**. `legacy_migration_approved=false`.

## 6. 구조 (검증 경로)

```
FRC-08 VERIFY
  ├─ (재사용) fpr13-isolated-final --include-lifecycle → installer_lifecycle PASS
  ├─ (재사용) w17-fc-build Launcher + Setup 0.1.18 지문
  ├─ (오늘)   _check_fpr13_runner --contracts-only → 17 PASS
  └─ (하지 않음) 공개 home migration / legacy_migration_approved

FRC-08W VERIFY
  ├─ 가용성 프로브 → 클린 2nd OS 없음
  └─ BLOCKED (제약 문서화만)
```

## 7. 조치

1. 추적표 FRC-08 → PARTIAL, FRC-08W → BLOCKED(가용성 제약)로 갱신.
2. FRC-08 잔여가 필요하면 임시 확장 공개 경계만 별도 단위로 잡는다. L6 재실행은 기본 불필요.
3. FRC-08W는 클린 Windows(또는 관리 가능 VM)가 생길 때까지 재개하지 않는다.
4. `legacy_migration_approved`·커밋·push는 요청 전까지 유지.
