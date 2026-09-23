# 라이선스 스캔 리포트

| 항목 | 내용 |
|------|------|
| 생성일 | 2026-09-23 |
| 방법 | `.venv` / `.venv-voice` `importlib.metadata` + `LICENSE.md` §3 |
| 결론 | **GPLv3 배포 충돌 0** (아래 주의 1건 문서화) |

---

## 1. 핵심 런타임 (`requirements.txt`) — 실측

| 패키지 | 버전(실측) | License-Expression / License | GPLv3 |
|--------|------------|------------------------------|:----:|
| PyQt6 | 6.11.0 | GPL-3.0-only | ✅ 제약 근원 |
| PyQt6-WebEngine | 6.11.0 | GPL-3.0-only | ✅ |
| psutil | 7.2.2 | BSD-3-Clause | ✅ |
| mss | 10.2.0 | MIT | ✅ |
| Pillow | 12.3.0 | MIT-CMU | ✅ |
| Markdown | 3.10.2 | BSD-3-Clause | ✅ |
| python-dotenv | 1.2.2 | BSD-3-Clause | ✅ |
| PyYAML | 6.0.3 | MIT | ✅ |
| pynput | 1.8.2 | LGPLv3 | ✅ |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | ✅ |
| numpy | 2.5.2 | BSD/MIT 복합 | ✅ |
| onnxruntime | 1.29.0 | MIT | ✅ |
| openai | 3.3.1 | Apache-2.0 | ✅ |
| anthropic | 1.0.0 | MIT | ✅ |
| pypdf | 6.16.2 | BSD-3-Clause | ✅ |
| pytesseract | 0.3.13 | Apache-2.0 | ✅ |
| **PyMuPDF** | 1.28.2 | **AGPL-3.0 OR Commercial** | ✅\* |
| comtypes | 1.4.16 | MIT | ✅ |
| pywin32 | 312 | PSF | ✅ |

\* PyMuPDF 무료 휠은 AGPL-3.0. FSF 기준 AGPL-3.0 ↔ GPL-3.0 **결합 가능**(결합 결과는 네트워크 조항이 더 강한 AGPL 쪽이 적용될 수 있음). IRIS는 이미 GPL-3.0-or-later이므로 **라이선스 충돌(배포 불가)은 아님**. 상용 재라이선스 시 Artifex 상업 라이선스 또는 PDF 경로를 `pypdf`만으로 제한하는 검토가 필요.

---

## 2. 선택 음성 (`requirements-voice*.txt`) — 실측

| 패키지 | 버전 | 라이선스 | GPLv3 |
|--------|------|----------|:----:|
| faster-qwen3-tts | 0.3.2 | **MIT** | ✅ |
| qwen-tts | 0.1.1 | Apache-2.0 | ✅ |
| mutagen | 1.48.1 | GPL-2.0-or-later | ✅ |
| soxr | 1.1.0 | LGPL-2.1-or-later | ✅ |
| fastapi | 0.140.0 | MIT | ✅ |

---

## 3. 벤더링 / 미번들

| 대상 | 라이선스 | 비고 |
|------|----------|------|
| `integrations/archify/` | MIT | `THIRD_PARTY_NOTICES.md` |
| `integrations/showui-aloha/` | Apache-2.0 | 별도 프로세스 |
| Ollama / Hermes | 업스트림 | HTTP만, 소스 미포함 |
| Eclipse Theia (IRIS IDE) | EPL-2.0 OR GPL-2.0+Classpath | 별도 Node 프로세스 |

---

## 4. 충돌 판정

| 검사 | 결과 |
|------|------|
| GPL-2.0-**only** 의존성 | 없음 |
| 독점/비상업 전용 의존성 | 없음 |
| CC BY-NC 코드 의존성 | 없음 |
| 고지 누락(벤더링) | archify·ShowUI-Aloha 고지 존재 |

**스캔 충돌: 0건.**

재생성:

```powershell
.venv\Scripts\python.exe -c "import importlib.metadata as m; print(m.metadata('PyQt6').get('License-Expression'))"
```

고지 전문·요약: [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) · [`LICENSE.md`](../../LICENSE.md).
