# PHASE 14 Gate Policy Reformation

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE14-GATE-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | EXECUTION OVERRIDE · Final Integration NO-GO · Full Absorption |
| 대상 | Development / Integration / Cutover / Migration / Production gates |
| 목적 | NO-GO를 개발 중단 조건에서 분리하고 배포·비가역 작업만 차단 |

## 1. 결론

기존 Product Stability / Final Gate **NO-GO는 유지**한다. 다만 적용 범위는 **공개 배포와 비가역적 사용자 환경 변경**으로 한정한다.

Hermes 완전 흡수, Owned Core 일체화, 결함 수정, 격리 환경 전환·회귀는 NO-GO와 무관하게 계속한다.

## 2. Gate 표

| Gate | GO 조건 | NO-GO / BLOCKED가 막는 것 | 막지 않는 것 |
|---|---|---|---|
| Development | 가역적 소스·계약·격리 작업 | 없음 (기본 GO) | 흡수·수정·레거시 격리 |
| Integration | 격리 홈에서 Owned 설치·실행·모델 검증 | 실사용 홈 강제 전환 | 격리 비교·재현 |
| Developer Cutover | 백업·Rollback·핵심 권한 경로 검증 | 조건부 전 전환 | 개발자 슬롯 실험(명시 승인 시) |
| Migration | 데이터 보존·복구 검증 + 승인 | `legacy_migration_approved` 승격 | 마이그레이션 설계·드라이런 |
| Production Release | 필수 검증 전부·보안·회귀 없음 | 공개 배포·설치본 공표 | 내부 개발 빌드 |

## 3. 정본 규칙

1. 향후 개발 정본은 **Iris Agent Owned Core**다.
2. Reference Core는 비교·임시 복구만. 신규 기능의 정본으로 쓰지 않는다.
3. 실패한 테스트 삭제·기준 완화로 PASS를 만들지 않는다.
4. 실제 실행 증거 없이 Independent Product Release GO를 선언하지 않는다.

## 4. 조치

1. PHASE 00 추적표에 본 정책을 상위 제약으로 둔다.
2. 각 Phase 보고의 Gate 판정란에 위 5-gate를 명시한다.
3. 사용자 데이터 삭제·승격·push·공개 Release는 별도 승인 전 금지.
