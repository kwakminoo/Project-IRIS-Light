# Contributing to IRIS

IRIS는 **Open Source Desktop AI Agent Runtime** (GPL-3.0-or-later)입니다.
기여는 환영합니다. PR을 보내면 해당 변경을 **GPL-3.0-or-later**로 제공하는 데 동의한 것으로 봅니다.

---

## 빠른 시작

```powershell
git clone https://github.com/kwakminoo/Project-IRIS-Light.git
cd Project-IRIS-Light
.\setup.bat          # 또는 .\setup.ps1
.\run.bat
```

문서: [`docs/domain.md`](docs/domain.md) · [`docs/ia/IA.md`](docs/ia/IA.md) · [`docs/guides/extending-iris.md`](docs/guides/extending-iris.md)

---

## 어디에 기여할까

| 우선 | 경로 | 설명 |
|------|------|------|
| 권장 | `integrations/hermes-skills/` | 새 스킬 — **코어 diff=0** |
| 권장 | `docs/` · `_check_*.py` | 문서·회귀 |
| 주의 | `iris/ui/` | HUD — PyQt6 GPL 결합 |
| 최소화 | `iris/runtime/`, `iris/system/`, `iris/infrastructure/` | Core — 버그/보안 위주 |

상세: [`docs/guides/extending-iris.md`](docs/guides/extending-iris.md)

---

## 체크 (PR 전)

```powershell
# 핵심 스모크 묶음
powershell -ExecutionPolicy Bypass -File scripts\run_core_smoke.ps1

# 또는 관련 모듈만
.venv\Scripts\python.exe -m iris.ui._check_control_scenarios
```

기능 재현: [`docs/검증/기능테스트-시나리오서.md`](docs/검증/기능테스트-시나리오서.md)

---

## 라이선스 — 금지

새 의존성·벤더링 시:

- **금지:** 독점, GPL-2.0-**only**, CC BY-**NC**, 연구용/비상업 전용 커스텀
- **필수:** 벤더링 시 원본 `LICENSE` + 출처 (`integrations/showui-aloha/` 방식)
- 표 갱신: `LICENSE.md` §3 · `THIRD_PARTY_NOTICES.md`

근거: [`LICENSE.md`](LICENSE.md) §8 · 스캔: [`docs/검증/license-scan-report.md`](docs/검증/license-scan-report.md)

---

## PR / Issue

- Issue·PR 템플릿: `.github/`
- Good first issue 라벨 이슈를 먼저 보세요
- UI 툴킷 전환은 문서만: [`docs/guides/ui-toolkit-migration.md`](docs/guides/ui-toolkit-migration.md) (풀 전환 PR은 일정 외)

---

## 문서 톤 (에이전트·인간)

패키지 헤더 규칙: [`docs/guides/agent-readable-docs.md`](docs/guides/agent-readable-docs.md)
