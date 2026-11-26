# PHASE 14 Gate Policy Reformation

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE14-GATE-2026-11-26 |
| 작성일 | 2026-11-26 |
| 갱신 | 2026-11-26 FINAL EXECUTION AUTHORIZATION |
| 관련 | EXECUTION OVERRIDE · Final Integration NO-GO · Full Absorption · Continuous Implementation |
| 대상 | Development / Integration / Cutover / Migration / Production gates |
| 목적 | NO-GO를 공개 배포·비가역 사용자 작업에만 한정하고, 개발·흡수·개발환경 전환은 계속 |

## 1. 결론

Product Stability / Final Gate의 **공개 릴리스 NO-GO는 유지**한다.

FINAL EXECUTION AUTHORIZATION에 따라 NO-GO는 아래를 **막지 않는다**.

- 가역적 코드 수정
- 신규 엔진 설치·테스트
- Hermes 기술 흡수
- Native Runtime 일체화
- 안전 조건을 충족한 **개발 환경** Owned 전환
- 검증된 레거시 정상 실행 경로 제거
- 제품 내부 테스트 빌드

여전히 별도 승인이 필요한 것: 사용자 데이터 영구 삭제, 복구용 백업 영구 삭제, **전체 사용자 대상** 마이그레이션 승격, 공개 배포, 요청 없는 commit/push.

## 2. Gate 표

| Gate | GO 조건 | NO-GO / BLOCKED가 막는 것 | 막지 않는 것 |
|---|---|---|---|
| Development | 가역적 소스·계약·격리 작업 | 없음 (기본 GO) | 흡수·수정·레거시 격리 |
| Integration | 격리 홈에서 Owned 설치·실행·모델 검증 | 전체 사용자 강제 전환 | 격리 비교·재현·설치 |
| Developer Cutover | 백업·Rollback·핵심 모델/도구/권한 경로 검증 | 조건 미충족 시 전환 | **본 승인으로** 조건 충족 후 개발 홈 Owned 전환 |
| Migration (전체 사용자) | 데이터 보존·복구 검증 + 별도 승인 | `legacy_migration_approved` 공개 승격 | 마이그레이션 설계·드라이런·개발 슬롯 |
| Production Release | 필수 검증 전부·보안·회귀 없음 | 공개 배포·설치본 공표 | 내부 개발 빌드 |

## 3. Developer Cutover 안전 조건 (사전 승인됨)

다음이 모두 충족되면 추가 승인 대기 없이 개발 환경 전환을 수행한다.

1. 최신 Owned Core 설치 및 Import 확인
2. 핵심 모델·도구 왕복 검증
3. 권한·승인 경로 검증
4. 사용자 데이터 백업
5. 격리 환경 Rollback 성공
6. 실제 복구 가능성 확인 (Reference Core 슬롯 보존)

개발 환경 전환 ≠ 전체 사용자 마이그레이션 승격.

## 4. 정본 규칙

1. 향후 개발 정본은 **Iris Agent Owned Core**다.
2. Reference Core는 비교·복구만. 정상 제품 실행 경로에서 제외한다.
3. 실패한 테스트 삭제·기준 완화로 PASS를 만들지 않는다.
4. 실제 실행 증거 없이 Independent Product Release GO를 선언하지 않는다.
5. Hermes 원본 흡수 소스가 IRIS 내부에 있는 것은 허용. 라이선스·출처 고지는 유지.

## 5. 조치

1. PHASE 00 추적표에 본 정책(FINAL EXEC)을 상위 제약으로 둔다.
2. 격리 Owned `0.1.1` rematerialize → 설치·Import → FIG-03 → Gate B → 13FPR → 안전조건 충족 후 개발 cutover.
3. 공개 Release와 전체 사용자 migration 승격은 별도 승인 전 금지.
