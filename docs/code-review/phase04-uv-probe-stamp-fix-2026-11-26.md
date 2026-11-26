# PHASE 04 — uv-probe stamp API 정렬

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE04-UV-PROBE-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | R-UV-PROBE · engine-uv-probe-boost · Gate A |
| 대상 | `_check_uv_probe_boost_no_editable` · `_finish_staged_install` |
| 목적 | stamp kwarg drift로 깨진 설치 자검을 현재 API에 맞춰 녹색으로 고정 |

## 1. 결론

체크가 옛 `_finish_staged_install(..., stamp=...)`를 호출해 TypeError로 죽었다. 실제 finish는 uv sync → `_probe_owned_slot` → activate만 탄다. 체크를 그 시그니처에 맞추고, uv 성공·probe miss·uv 없음 세 경우 모두 `pip install -e`가 없음을 유지했다. 자검 exit 0.

## 2. 원인·조치

| 항목 | 내용 |
|---|---|
| 원인 | 체크만 구 API(`stamp`/`command`/`probe_gateway`) 유지. 구현은 stamp 제거 |
| 조치 | 체크만 갱신. 프로덕션 시그니처·editable 금지 계약은 유지·강화 |
| 증거 | `.venv\Scripts\python.exe -m iris.system._check_uv_probe_boost_no_editable` → `ok` · exit 0 |

## 3. 조치

1. R-UV-PROBE COMPLETE.
2. `_check_uv_probe_boost_only` 등 동일 stamp 호출이 있으면 같은 API로 정렬.
3. 커밋·push·라이브 홈 미실시.
