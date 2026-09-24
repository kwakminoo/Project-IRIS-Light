# Setup.exe「Python packages did not finish」— 원인 · 이력 · 개선안

> **작성**: 2026-09-25  
> **재현**: IRIS-Setup 설치 직후 Inno `ssPostInstall` → `setup.ps1 -Recreate`  
> **이번 UI**: `FAIL: 스크립트 오류: 'python.exe' 경로에 대한 액세스가 거부되었습니다.`  
> **관련**: `setup.ps1`, `setup.bat`, `installer/iris.iss`, `scripts/_check_setup_venv_retire.ps1`  
> **총괄표**: 연번 **23**

---

## 1. 한줄 결론

| # | 판정 | 내용 |
|---|------|------|
| A | **확정** | Inno가 항상 `-Recreate`로 `.venv`를 `Remove-Item`하는데, 실행 중 IRIS/`.venv\python.exe`·AV 잠금이면 **UnauthorizedAccessException** → trap → 위 한국어 메시지 |
| B | **이전과 별건** | Store 스텁·Cua PATH(448)·pip SSL·깨진 빈 `.venv` 는 0.1.7–0.1.13에서 이미 완화. **이번은 파일 잠금** |
| C | **금지 회귀** | 같은 증상에서 다시 `Remove-Item -Force`만 / `SilentlyContinue`만 / Inno 동일 `-Recreate` 2회만 으로 때리지 말 것 |

---

## 2. 설치 파이프라인 (Setup.exe)

```
IRIS-Setup.exe (Inno)
  └─ ssPostInstall
        └─ powershell setup.ps1 -Recreate   (실패 시 동일 인자 1회 재시도)
              ├─ Python 탐색 (Store 스텁 제외 · winget/공식 bootstrap)
              ├─ .venv 삭제(-Recreate) ← ★ Access Denied 진원
              ├─ pip install -r requirements.txt (PATH Cua scrub · trusted-host 재시도)
              └─ import 검증 → 실패 시 .venv 재생성 1회
```

앱 안 Core「Hermes 설치」(총괄표 22)와는 **단계가 다름**. 본 문서는 **패키지/venv 단계**만.

---

## 3. 지금까지 나온 Setup 관련 문제 · 조치 · 상태

| ID | 증상 / 메시지 | 원인 | 쓴 해결 | 상태 | 다시 쓸 때 |
|----|---------------|------|---------|------|------------|
| S1 | Store `WindowsApps\python.exe` 스텁으로 실패 | 0바이트/별칭 | `Test-RealPythonExe` 제외 · known path · bootstrap | **완료** | 스텁 허용으로 되돌리지 말 것 |
| S2 | pip 중 `WinError 448` / Cua 정션 | PATH의 깨진 마운트 | `Set-PipSafePath` 에서 Cua·접근불가 구간 제거 | **완료** | PATH 전체 삭제보다 스크럽 유지 |
| S3 | 빈/깨진 `.venv` 재사용 → 검증 실패 | `pyvenv.cfg` 없음 · 중도 실패 | 자동 wipe + 검증 실패 시 1회 재생성 · Inno `-Recreate` | **완료** | wipe를 SilentlyContinue만 하지 말 것(반쯤 남음) |
| S4 | SSL/프록시 pip 실패 | 기업망 | `--trusted-host` 재시도 · pip 로그 꼬리 | **완료** | trusted-host를 기본 1순위로 올리지 말 것 |
| S5 | Setup 대화상자에 원인 공백 | UTF-16 transcript / Fail 미기록 | `setup-fail-reason.txt` UTF-8 BOM `FAIL:` | **완료** | |
| S6 | Hermes Core 우회 UI가 Obtaining만 표시 | head 절단 · uv 448 | 총괄표 **22** · 꼬리 로그 · prefer_bypass | **완료** | Setup venv와 혼동 금지 |
| S7 | **`'python.exe' 경로에 대한 액세스가 거부`** | `-Recreate` `Remove-Item` + 잠금 프로세스/AV | **프로세스 종료 → 재시도 → rename trash → robocopy wipe** (`Remove-TreeSafe`) | **이번 조치** | Remove-Item만 / 무시만 / 동일 Inno 재시도만 **재시도 금지** |

### 미해결 · 관측 대기

| ID | 내용 | 비고 |
|----|------|------|
| S8 | Controlled Folder Access / 일부 EDR이 rename까지 막을 때 | Fail 힌트에 예외 경로 안내. 코드만으로 완전 우회 불가 |
| S9 | `/VERYSILENT` 시 MsgBox 없음 | 로그·`setup-fail-reason.txt`만 — 의도적 |
| 연번 21 | OS 파일 드롭 | Setup과 무관 · 총괄표 미해결 |

---

## 4. 확정 결함 (S7) — 수정 전

```powershell
# setup.ps1 (수정 전) + iris.iss 가 항상 -Recreate
if ($Recreate -and (Test-Path $VenvPath)) {
    Remove-Item -Recurse -Force $VenvPath   # ← 잠금 시 trap
}
```

`$ErrorActionPreference = "Stop"` + `trap { Fail "스크립트 오류: $m" }` 이라  
예외 문구가 그대로 Setup 창에 뜸.

---

## 5. 개선안 (구현)

| 연번 | 조치 | 위치 |
|:---:|------|------|
| 1 | `Stop-IrisVenvHolders` — `.venv` 트리·`IRIS.exe` 잠금 프로세스 종료 | `setup.ps1` |
| 2 | `Remove-TreeSafe` — 재시도 삭제 → rename `*.trash-*` → robocopy/삭제 · trash ≤3 | `setup.ps1` |
| 3 | `-Recreate` / 깨진 venv / 검증 후 재생성 전부 `Remove-TreeSafe` | `setup.ps1` |
| 4 | `Test-VenvUsable`이 python.exe **접근 가능**까지 확인 | `setup.ps1` |
| 5 | 잠금 전용 Fail 힌트 (IRIS 종료 · 백신 예외) | `setup.ps1` |
| 6 | 자검 `scripts/_check_setup_venv_retire.ps1` (잠금→rename) | scripts |
| 7 | Setup **0.1.14** 재배포 | `installer/iris.iss` |

---

## 6. 앞으로 같은/유사 오류가 뜨면

1. **먼저** 이 문서 §3 표에서 ID를 고른다.  
2. **이미 완료된 해결을 그대로 반복하지 않는다** (C열「다시 쓸 때」).  
3. 새 가설이면 표에 행을 추가하고, 총괄표 연번 23 §이력에 한 줄 남긴다.  
4. Hermes Core 단계면 이 문서가 아니라 `Hermes설치실패-원인과-개선안.md`(연번 22).

---

## 7. 검증

```powershell
powershell -ExecutionPolicy Bypass -File scripts\_check_setup_venv_retire.ps1
powershell -ExecutionPolicy Bypass -File scripts\_check_setup_python_discover.ps1
# 배포
powershell -ExecutionPolicy Bypass -File scripts\build_iris_setup.ps1
```

| # | 기준 |
|---|------|
| 1 | 잠금 파일에서도 original `.venv` 경로가 비고 자검 초록 |
| 2 | Setup 0.1.14 cold/재설치 시 packages 단계 exit 0 (IRIS 종료 상태에서) |
| 3 | IRIS 실행 중 재설치해도 Access Denied trap 문구로 바로 죽지 않음 |

---

## 8. 상태

| 항목 | 상태 |
|------|------|
| S7 원인 확정 | 완료 |
| Remove-TreeSafe 구현 | 완료 |
| 자검 | `_check_setup_venv_retire.ps1` |
| Setup 0.1.14 업로드 | 빌드·publish 시 갱신 |
