# UI 툴킷 전환 가이드 (PyQt6 → PySide6)

| 항목 | 내용 |
|------|------|
| 목적 | 라이선스 유연성(LGPL 경로) 증명 — **가이드만**. 실제 전환은 제출 일정상 비권장 |
| 근거 | `LICENSE.md` §5 · 교수님 피드백 No.10 |
| 작성일 | 2026-09-23 |

> YAGNI: 이 문서만으로 “다른 UI로도 전환 가능”을 입증한다. 풀 마이그레이션 PR은 열지 말 것.

---

## 1. 왜 전환을 말하는가

| 현재 | 전환 후(가능 경로) |
|------|-------------------|
| PyQt6 = **GPL-3.0-only** → IRIS 전체가 GPL 결합 | PySide6 = **LGPL-3.0** → 이론상 MIT/Apache로 내려갈 **전제** 충족 |
| `iris/ui/` 전역이 PyQt6 import | UI 레이어만 교체, Runtime/Gateway는 유지 |

---

## 2. 모듈 경계 (손대는 곳 / 안 건드리는 곳)

```text
바꾸기 대상 (Presentation)
  iris/ui/**          ← PyQt6 위젯·시그널·QThread
  IRIS.spec           ← hiddenimports / Qt 플러그인 경로
  scripts/build_iris_exe.ps1 등 빌드 스크립트

건드리지 않기 (Core / Extension)
  iris/runtime/**     ← UserTurnDispatcher
  iris/system/**      ← setup_protocol, hermes_gateway, control_surface
  iris/infrastructure/**
  iris/mcp/**
  integrations/hermes-skills/**
  services/voice_runtime/**
```

**계약:** UI는 Gateway HTTP/시그널로만 런타임과 대화한다. UI 툴킷을 바꿔도 `ollama_client` / `hermes_client` API는 동일해야 한다.

실측: `iris/**/*.py`에서 `PyQt6`를 직접 import하는 파일이 **100개 전후** — 대부분 `iris/ui/`.

---

## 3. 기계적 치환 체크리스트

| 단계 | 내용 | 주의 |
|:----:|------|------|
| 1 | `requirements.txt`: `PyQt6*` → `PySide6`, `PySide6-Addons`/`WebEngine` 대응 패키지 | 버전 핀 재검증 |
| 2 | import: `from PyQt6.QtXxx` → `from PySide6.QtXxx` | 일괄 sed 가능 |
| 3 | 시그널: `pyqtSignal` → `Signal` (`PySide6.QtCore`) | 슬롯 데코레이터도 확인 |
| 4 | 슬롯: `pyqtSlot` → `Slot` | |
| 5 | `sip` / Riverbank 전용 API 제거 | PySide는 shiboken |
| 6 | WebEngine: `PyQt6.QtWebEngine*` → `PySide6.QtWebEngine*` | 임베디드 뷰 회귀 |
| 7 | `IRIS.spec` Qt 바이너리·플러그인 경로 재작성 | thin launcher면 영향 적음 |
| 8 | ShowUI-Aloha: 이미 PySide6 — **같은 프로세스 import 금지** 유지 (`AlohaBridge`) | LICENSE.md §3.3 |

---

## 4. 회귀 `_check_*` (전환 후 필수)

우선순위 높은 것:

```powershell
.venv\Scripts\python.exe -m iris.ui._check_iris_startup
.venv\Scripts\python.exe -m iris.ui._check_setup_protocol
.venv\Scripts\python.exe -m iris.ui._check_hermes_required
.venv\Scripts\python.exe -m iris.ui._check_control_scenarios
.venv\Scripts\python.exe -m iris.ui._check_iris_ide_companion_tile
powershell -ExecutionPolicy Bypass -File scripts\run_core_smoke.ps1
```

사람 검증: [`docs/검증/기능테스트-시나리오서.md`](../검증/기능테스트-시나리오서.md) 시나리오 D.

---

## 5. 전환 후에도 남는 작업 (LICENSE.md §5)

1. pynput(LGPL) / mutagen(GPL-2.0+) 재검토  
2. PyMuPDF(AGPL dual) 재검토  
3. 전체 회귀 후 프로젝트 라이선스를 Apache-2.0 등으로 **별도 결정**  

일정 촉박 시 **이 가이드 + GPL-3.0-or-later 유지**가 권장 포지션이다.
