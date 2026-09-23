# Third-party notices

IRIS(Iris Light)가 **의존·벤더링·선택 설치**하는 제3자 소프트웨어 고지.
프로젝트 라이선스 근거·호환 표는 [`LICENSE.md`](LICENSE.md).
스캔 실측: [`docs/검증/license-scan-report.md`](docs/검증/license-scan-report.md).

생성일: 2026-09-23 · 동기화 기준: `requirements.txt` + `services/voice_runtime/requirements-voice*.txt` + `integrations/`

---

## 1. 핵심 Python 의존성 (요약)

아래는 PyPI 메타데이터 기준. 전문은 각 패키지 배포물을 따른다.

| 패키지 | 라이선스 | 출처 |
|--------|----------|------|
| PyQt6, PyQt6-WebEngine | GPL-3.0-only | Riverbank / PyPI |
| PyQt6-Qt6, PyQt6-WebEngine-Qt6 | LGPL-3.0 | The Qt Company (휠 경유) |
| PyQt6-sip | BSD-2-Clause | PyPI |
| psutil | BSD-3-Clause | PyPI |
| mss | MIT | PyPI |
| Pillow | MIT-CMU (HPND) | PyPI |
| Markdown | BSD-3-Clause | PyPI |
| python-dotenv | BSD-3-Clause | PyPI |
| PyYAML | MIT | PyPI |
| pynput | LGPL-3.0 | PyPI |
| opencv-python-headless | Apache-2.0 | PyPI |
| numpy | BSD-3-Clause 외 | PyPI |
| onnxruntime | MIT | PyPI |
| openai | Apache-2.0 | PyPI |
| anthropic | MIT | PyPI |
| pypdf | BSD-3-Clause | PyPI |
| pytesseract | Apache-2.0 | PyPI |
| PyMuPDF (pymupdf) | AGPL-3.0 OR Commercial | Artifex / PyPI |
| comtypes | MIT | PyPI (Windows) |
| pywin32 | PSF-2.0 | PyPI (Windows) |

---

## 2. 선택 음성 런타임 (요약)

| 패키지 | 라이선스 | 비고 |
|--------|----------|------|
| faster-qwen3-tts | MIT | `requirements-voice-full.txt` |
| qwen-tts | Apache-2.0 | 코드; 모델 가중치는 별도 |
| mutagen | GPL-2.0-or-later | |
| soxr | LGPL-2.1-or-later | |
| fastapi, uvicorn, starlette 등 | MIT / BSD | `requirements-voice.txt` |
| torch / torchaudio 등 | BSD계 | Full 설치 시 |

모델 가중치·음성 녹음 데이터는 코드 라이선스와 분리 — `LICENSE.md` §4.

---

## 3. 벤더링 코드

### 3.1 archify

- 위치: `integrations/archify/`
- 출처: https://github.com/tt-a1i/archify (커밋 `72c750bb070d95171dbb2244e5b62b1b7da69c12`)
- 라이선스: MIT — 전문은 `integrations/archify/LICENSE`
- archify 자신의 제3자 고지: `integrations/archify/THIRD_PARTY_NOTICES.md`

```
MIT License

Copyright (c) 2026 tt-a1i (Archify)
Copyright (c) 2025 Cocoon AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the Software), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED AS IS, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 3.2 ShowUI-Aloha

- 위치: `integrations/showui-aloha/`
- 출처: https://github.com/showlab/ShowUI-Aloha
- 라이선스: Apache-2.0 — `integrations/showui-aloha/LICENSE`, `UPSTREAM.md`
- 실행: IRIS와 **별도 프로세스** (`AlohaBridge`) — PySide6를 본 프로세스에 import하지 않음

---

## 4. 번들하지 않는 런타임 (고지)

| 대상 | 관계 | 라이선스 |
|------|------|----------|
| Ollama | HTTP `:11434` | MIT (업스트림) |
| Hermes Agent | HTTP `:8642` | 업스트림 조건 |
| Eclipse Theia (IRIS IDE) | 선택 Node 프로세스 | EPL-2.0 OR GPL-2.0-only WITH Classpath-exception-2.0 |
| Silero VAD ONNX | 실행 시 다운로드 | MIT |

---

## 5. 재동기화

의존성을 바꾸면:

1. `LICENSE.md` §3 표 갱신
2. 본 파일 요약 표 갱신
3. `docs/검증/license-scan-report.md` 재실측
4. GPL-2.0-only / NC / 독점 라이선스는 PR 거부 (`CONTRIBUTING.md`)
