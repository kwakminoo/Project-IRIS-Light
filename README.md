# IRIS

**유료 AI 구독·복잡한 설치 없이, 내 PC에서 바로 쓰는 오픈소스 데스크톱 AI 에이전트.**

IRIS는 [Ollama](https://ollama.com/)(로컬/클라우드 모델)와 [Hermes Agent](https://hermes-agent.nousresearch.com/)(도구·스킬)를 자동으로 준비하고, 대화형 HUD로 묶는 **Python · PyQt6** 데스크톱 앱입니다.  
사용자는 자연어로 요청하고, IRIS는 Runtime Gateway를 통해 모델 응답과 파일·터미널·웹 도구 실행을 스트리밍으로 보여 줍니다.

> 버전 `0.1.0-light` · 표시 이름 **IRIS** · 코드/패키지명 Iris Light

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6.svg)](#필요-사양)

---

## 🎬 설치·동작 데모 영상

**설치부터 실제 동작까지 3분** — 썸네일을 누르면 유튜브로 이동합니다.

<!-- DEMO_VIDEO:START -->
<!--
  ⚠ 영상 업로드 후 아래 두 줄의 주석을 풀고 VIDEO_ID 를 실제 값으로 바꾸세요.
     VIDEO_ID = https://youtu.be/여기11자리
     대본·업로드 가이드: docs/demo-video-script.md
-->
<!--
[![IRIS 설치·동작 데모](https://img.youtube.com/vi/VIDEO_ID/maxresdefault.jpg)](https://youtu.be/VIDEO_ID)
-->

> 📹 **영상 준비 중입니다.** 촬영 대본과 업로드 절차는 [`docs/demo-video-script.md`](docs/demo-video-script.md)에 있습니다.
<!-- DEMO_VIDEO:END -->

---

## ⚡ 3분 만에 시작하기

**파이썬을 처음 써 보는 분도 명령어 입력 없이 설치할 수 있습니다.**

<table>
<tr><td align="center"><b>1</b></td><td>저장소를 <code>Code → Download ZIP</code> 으로 받아 압축을 풉니다.</td></tr>
<tr><td align="center"><b>2</b></td><td>폴더 안의 <b><code>setup.bat</code> 을 더블클릭</b>합니다. — 파이썬 확인 · 가상환경 · 패키지 설치 · 검증까지 <b>전부 자동</b></td></tr>
<tr><td align="center"><b>3</b></td><td><b><code>run.bat</code> 을 더블클릭</b>합니다. 시작 위저드가 Ollama · Hermes 설치를 이어서 안내합니다.</td></tr>
</table>

끝입니다. 자세한 설치 옵션과 문제 해결은 [설치](#설치) 절을 보세요.

---

## 문제 정의

- 최신 AI 도구는 **구독비**와 **설치·연동 복잡도** 때문에 학생·취준생·초보 개발자에게 진입 장벽이 큽니다.
- “모델만 돌리기”와 “실제 PC에서 코딩·문서·파일 작업을 시키는 에이전트” 사이에는 여전히 큰 간격이 있습니다.
- IRIS는 **Ollama + Hermes를 PC 환경에 맞게 자동 설치·연결**해, 비용 부담 없이 코딩 학습·프로젝트·업무 자동화를 경험할 수 있는 **로컬 우선 오픈소스 환경**을 목표로 합니다.

---

## 한눈에 보는 구조

```text
[사용자 자연어]
       │
       ▼
[IRIS HUD — PyQt6]
  Chat · Monitor · Wiki · Email · Calendar · Settings
       │
       ▼
[Runtime Gateway]
  ollama_client · hermes_client · setup_protocol
       │
       ├──────────────► [Ollama :11434]   모델 추론 (로컬/클라우드)
       │
       └──────────────► [Hermes :8642]    도구·스킬 (파일·터미널·웹·MCP…)
```

IRIS는 웹검색·셸·파일 IO를 자체 재구현하지 않습니다.  
**세션·권한·스트리밍 UI·시작 프로토콜**을 담당하고, 실행은 Ollama/Hermes에 위임합니다.

자세한 IA: `[docs/ia/IA.md](docs/ia/IA.md)` · 도메인: `[docs/domain.md](docs/domain.md)`

---

## 주요 기능


| 영역            | 내용                                                                     |
| ------------- | ---------------------------------------------------------------------- |
| **시작 프로토콜**   | 첫 실행 시 Ollama·최소 모델·Hermes 설치/기동·provider·gateway·MCP 연동을 단계적으로 안내·자동화 |
| **대화형 HUD**   | 모델 선택, 대화 이력, 사고/도구 로그, 실시간 스트리밍                                       |
| **에이전트 실행**   | Hermes를 통한 파일·터미널·웹 등 도구 호출 (스킬·MCP 포함)                                |
| **Control Surface** | Hermes→UI 역제어 (`:8765`) · iris-control 스킬·MCP                          |
| **시스템 모니터**   | 창/리소스 인식, 알림 정책, Live Activity, (옵션) 전화/알림 낭독                          |
| **이메일**       | 다중 계정 메일 워크스페이스                                                        |
| **캘린더**       | 일정 워크스페이스 + 공휴일·에이전트 연동                                                 |
| **IDE Companion** | IDE 타일 배치·바이브코딩 연동                                                    |
| **Iris Wiki** | Obsidian vault 기반 프로젝트 문서 + `~/.iris-light/iris-wiki` 사용자 노트           |
| **로컬 저장**     | 설정·프로필 등 SQLite (`~/.iris-light/`)                                     |
| **선택 확장**     | 음성 런타임(`:18765`), 화면 학습(Aloha), Android 에뮬레이터·mobile-mcp 등             |
| **준비 중**      | Instagram / Discord / Kakao / Telegram 워크스페이스                         |


---

## 필요 사양

### 소프트웨어

- **Windows 10/11** 권장 (시작 프로토콜·winget/Hermes 설치 스크립트 기준)
- Python **3.11+** 권장
- **안정적인 인터넷** 필수 (클라우드 모델·도구 호출)

### 하드웨어 (클라우드 모델 위주)

IRIS는 기본적으로 **클라우드 모델**로 추론하고, 로컬에는 UI·Hermes 게이트웨이·도구 실행만 둡니다.  
로컬 LLM용 GPU/VRAM은 필요하지 않습니다. 아래 저장 공간은 **IRIS 관련 설치분**(앱·venv·Ollama/Hermes 런타임, 대용량 로컬 모델·에뮬레이터 제외) 기준입니다.

| 구분 | 최소 | 권장 |
|------|------|------|
| **OS** | Windows 10/11 64bit | Windows 11 |
| **CPU** | 듀얼~쿼드코어 (사무용 i3 / Ryzen 3 이상) | i5 / Ryzen 5 이상 |
| **RAM** | **8GB** (가능하나 도구·브라우저 병행 시 빡쁨) | **16GB** |
| **GPU** | **불필요** | 불필요 |
| **저장 (IRIS만)** | 여유 **약 20GB** | 여유 **약 30GB** |
| **네트워크** | 인터넷 연결 | 지연 낮은 안정 회선 |

**참고**

- OS·다른 프로그램용 SSD 용량은 별도입니다. PC 구매 시에는 보통 256GB 이상을 권합니다.
- Android 에뮬레이터·화면 학습·로컬 대용량 모델을 쓰면 저장·RAM이 추가로 필요합니다.

---

## 설치

### 방법 A — 자동 설치 (권장)

저장소 폴더에서 **`setup.bat` 을 더블클릭**하면 끝입니다.
터미널을 열 필요도, 명령어를 외울 필요도 없습니다.

`setup.bat` → `setup.ps1` 이 다음을 순서대로 처리합니다.

| 단계 | 하는 일 | 실패하면 |
|:---:|------|------|
| 1 | Python 3.11+ 탐색 (`py -3.13/-3.12/-3.11` → `python`) | 설치 링크와 `winget` 명령을 화면에 안내 |
| 2 | 가상환경 `.venv` 생성 (이미 있으면 재사용) | `venv` 모듈 설치 방법 안내 |
| 3 | `pip` 업그레이드 | 경고만 남기고 기존 pip으로 계속 |
| 4 | `requirements.txt` 전체 설치 | 프록시·사내망용 대체 명령 안내 |
| 5 | `.env.example` → `.env` 복사 | 기존 `.env` 는 절대 덮어쓰지 않음 |
| 6 | PyQt6 등 핵심 패키지 **import 검증** | VC++ 재배포 패키지 설치 명령 안내 |

터미널에서 옵션을 주고 싶다면:

```powershell
.\setup.ps1              # 기본 설치
.\setup.ps1 -Run         # 설치 후 바로 실행
.\setup.ps1 -Voice       # 선택 음성 런타임(.venv-voice)까지 설치
.\setup.ps1 -Recreate    # .venv 를 지우고 새로 만들기 (설치가 꼬였을 때)
```

Linux / macOS:

```bash
chmod +x setup.sh
./setup.sh               # --run / --recreate 옵션 지원
```

> 실행 정책(`ExecutionPolicy`) 때문에 `.ps1` 이 막히는 환경에서도 `setup.bat` 은
> 정상 동작합니다. 내부에서 `-ExecutionPolicy Bypass` 로 우회합니다.

### 방법 B — 수동 설치

```powershell
git clone https://github.com/kwakminoo/Project-IRIS-Light.git
cd Project-IRIS-Light

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### 설치가 잘 안 될 때

| 증상 | 원인 · 해결 |
|------|------|
| `Python 3.11 이상을 찾지 못했습니다` | Python 미설치 또는 PATH 누락. 설치 시 **[Add python.exe to PATH]** 체크. `winget install -e --id Python.Python.3.12` |
| `이 시스템에서 스크립트를 실행할 수 없으므로` | `.ps1` 직접 실행이 막힌 경우. **`setup.bat` 을 쓰세요** |
| 가상환경 생성 실패 | Microsoft Store 버전 Python은 문제가 잦습니다. [python.org](https://www.python.org/downloads/) 배포판 권장. Debian 계열은 `sudo apt install python3-venv` |
| 패키지 설치 중 네트워크 오류 | 사내망/프록시. `pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org` |
| PyQt6 import 실패 | Windows: `winget install -e --id Microsoft.VCRedist.2015+.x64` · Linux: `sudo apt install libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0` |
| 그래도 안 될 때 | `.\setup.ps1 -Recreate` 로 가상환경을 통째로 다시 만들기 |

---

## 실행

```powershell
# 권장: run.bat (dist\IRIS.exe 또는 venv pythonw)
.\run.bat

# 또는
python -m iris
```

Linux/macOS:

```bash
chmod +x run.sh
./run.sh
# 또는: python3 -m iris
```

### 첫 실행

1. 앱이 **시작 위저드**를 띄웁니다.
2. Core 단계: Ollama 공식 설치·기동 → 최소 모델 pull → Hermes 설치 → API/provider 연결 → gateway 기동.
3. Optional(STT 음성·Full TTS·업무학습 Aloha·에뮬레이터·Node/mobile-mcp·클라우드 로그인 등)은 「설치」또는 「나중에」.
4. HUD 채팅에서 바로 자연어 요청을 보내면, Hermes/Ollama가 응답·도구 실행을 스트리밍합니다.

> 데모만 보려면: `IRIS_SETUP_DEMO=1` (실제 설치 없음)  
> UI 미리보기: `IRIS_SETUP_DRY_RUN=1`

---

## 프로젝트 구조

```text
iris/                 # 앱 본체
  ui/                 # PyQt6 HUD (채팅, 모니터, 위키, 메일, 캘린더, IDE, 설정…)
  system/             # setup_protocol, ollama_server, hermes_gateway, control_surface
  infrastructure/     # Ollama/Hermes/email/calendar HTTP 클라이언트
  runtime/            # UserTurnDispatcher · voice intents
  knowledge/          # Iris Wiki · Obsidian vault
  storage/            # SQLite 설정·프로필·메일 계정 등
  monitoring/         # 모니터·알림·콜
  learning/           # (선택) 화면 학습 Aloha
  audio/              # (선택) 음성 클라이언트 · VAD/AEC
  mcp/                # iris-control stdio
services/voice_runtime/  # (선택) FastAPI STT/TTS :18765
integrations/         # Hermes 스킬·플러그인, Aloha 등
docs/                 # 도메인·IA·API·음성 설계
obsidian-vault/       # 프로젝트 지식 베이스 (Wiki docs 소스)
scripts/              # 빌드·보이스 프로필·설치 보조 스크립트
setup.bat             # ★ 자동 설치 — 더블클릭 진입점 (Windows)
setup.ps1             # 자동 설치 본체 (Windows)
setup.sh              # 자동 설치 (Linux/macOS)
run.bat / run.sh      # 실행
.env.example          # 환경 설정 템플릿 (setup 이 .env 로 복사)
requirements.txt
LICENSE               # GPL v3 전문
LICENSE.md            # 라이선스 근거·서드파티 인벤토리
```

---

## 기술 스택


| 구분   | 기술                                                       |
| ---- | -------------------------------------------------------- |
| UI   | Python, PyQt6, PyQt6-WebEngine                           |
| 모델   | Ollama (OpenAI 호환 `/v1`)                                 |
| 에이전트 | Hermes Agent (gateway API, skills, MCP)                  |
| 저장   | SQLite (`~/.iris-light/`)                                |
| 지식   | Obsidian 호환 Markdown vault                               |
| 기타   | psutil, mss, openai/anthropic SDK 등 (`requirements.txt`) |


---

## 기대 효과

- **접근성**: 구독료·복잡한 에이전트 셋업이 부담인 학생·취준생·초보 개발자의 진입 장벽을 낮춥니다.
- **실습형 AI**: 답만 받는 소비를 넘어, 코딩·문서·파일 작업을 **로컬 PC에서 직접 수행**하며 활용 역량을 키웁니다.
- **격차 완화**: PC 사양에 맞는 모델을 연결해, 경제적·디지털 격차로 인한 AI 경험 불평등을 줄이는 데 기여합니다.
- **프라이버시·자립**: 로컬 실행으로 민감 정보 외부 전송을 줄이고, 네트워크·특정 벤더에만 의존하지 않는 사용이 가능합니다.

---

## 문서


| 문서                                                                             | 설명                                 |
| ------------------------------------------------------------------------------ | ---------------------------------- |
| `[docs/domain.md](docs/domain.md)`                                             | 바운디드 컨텍스트·Runtime Gateway 설계       |
| `[docs/ia/IA.md](docs/ia/IA.md)`                                               | 정보 구조·요청 경로·아키텍처 다이어그램              |
| `[docs/api/](docs/api/)`                                                       | API 관련 문서                          |
| `[docs/voice.md](docs/voice.md)`                                               | 음성 STT/TTS · 보이스 프로필               |
| `[docs/voice_architecture.md](docs/voice_architecture.md)`                     | 음성 런타임 경계·흐름                       |
| `[integrations/hermes-skills/README.md](integrations/hermes-skills/README.md)` | Iris Control Surface (Hermes ↔ UI) |
| `[LICENSE.md](LICENSE.md)`                                                     | 라이선스 근거 · 서드파티 인벤토리      |
| `[docs/demo-video-script.md](docs/demo-video-script.md)`                       | 데모 영상 촬영 대본 · 업로드 절차     |


---

## 기여

이슈·PR 환영합니다. 변경 전에는 가능하면 기존 `_check_*.py` 스모크나 관련 모듈 단위 확인을 돌려 주세요.

```powershell
# 예: IDE companion orphan 창 회귀 방지
py -3 -m iris.ui._check_ide_companion_windows
```

---

## 라이선스

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**GNU General Public License v3.0 이상 (`GPL-3.0-or-later`)** — 전문은 루트 [`LICENSE`](LICENSE).

`Copyright (C) 2026 IRIS Project Contributors`

### 왜 GPLv3인가

IRIS의 UI 전체는 **PyQt6** 위에 올라가 있고, PyQt6는 상업 라이선스를 구매하지 않는 한
**GPL-3.0-only** 입니다 (`License-Expression: GPL-3.0-only`). 저장소는 PyQt6를 번들한
`dist/IRIS.exe` 를 직접 배포하므로 이 조건이 이론이 아니라 실제로 적용됩니다.
따라서 **MIT·Apache-2.0은 선택할 수 없으며**, GPLv3 제약을 만족하는 것 중 가장
개방적인 선택이 `GPL-3.0-or-later` 입니다.

나머지 의존성은 모두 GPLv3와 호환됩니다 — mutagen(GPL-2.0-**or-later**),
pynput·soxr(LGPL), ShowUI-Aloha(Apache-2.0, 벤더링), 그 외 MIT/BSD/Apache/MPL-2.0.

전체 근거와 서드파티 라이선스 인벤토리, 모델 가중치·음성 데이터 취급, 더 개방적인
라이선스로 가는 경로는 **[`LICENSE.md`](LICENSE.md)** 에 정리돼 있습니다.

> 기여자 안내: 이 저장소에 보낸 PR은 GPL-3.0-or-later로 제공하는 데 동의하는 것으로
> 간주합니다. 새 의존성 추가 시 GPL-3.0 비호환 라이선스(독점, GPL-2.0-**only**,
> CC BY-**NC**, 비상업용 커스텀)는 받을 수 없습니다.

---

## 면책

IRIS는 Hermes 도구를 통해 로컬 파일·터미널에 영향을 줄 수 있습니다.  
중요한 작업 전에는 권한 설정과 확인 다이얼로그를 확인하세요. 프로덕션 자동화·무인 실행은 사용자 책임 하에 진행하세요.