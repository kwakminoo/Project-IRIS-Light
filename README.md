# IRIS

**유료 AI 구독·복잡한 설치 없이, 내 PC에서 바로 쓰는 오픈소스 데스크톱 AI 에이전트.**

IRIS는 [Ollama](https://ollama.com/)(로컬/클라우드 모델)와 [Hermes Agent](https://hermes-agent.nousresearch.com/)(도구·스킬)를 자동으로 준비하고, 대화형 HUD로 묶는 **Python · PyQt6** 데스크톱 앱입니다.  
사용자는 자연어로 요청하고, IRIS는 Runtime Gateway를 통해 모델 응답과 파일·터미널·웹 도구 실행을 스트리밍으로 보여 줍니다.

> 버전 `0.1.0-light` · 표시 이름 **IRIS** · 코드/패키지명 Iris Light

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
| **시스템 모니터**   | 창/리소스 인식, 알림 정책, Live Activity                                         |
| **이메일**       | 다중 계정 메일 워크스페이스                                                        |
| **Iris Wiki** | Obsidian vault 기반 프로젝트 문서 + `~/.iris-light/iris-wiki` 사용자 노트           |
| **캘린더**       | 일정 워크스페이스 + 에이전트 연동                                                    |
| **로컬 저장**     | 설정·프로필 등 SQLite (`~/.iris-light/`)                                     |
| **선택 확장**     | 음성 런타임, 화면 학습(Aloha), Android 에뮬레이터·mobile-mcp 등                       |


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

### 설치

```powershell
git clone <이-저장소-URL>
cd Project-IRIS-Light-main

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 실행

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
  ui/                 # PyQt6 HUD (채팅, 모니터, 위키, 메일, 설정…)
  system/             # setup_protocol, ollama_server, hermes_gateway
  infrastructure/     # Ollama/Hermes HTTP 클라이언트
  knowledge/          # Iris Wiki · Obsidian vault
  storage/            # SQLite 설정·프로필·메일 계정 등
  monitoring/         # 모니터·알림
  learning/           # (선택) 화면 학습
  audio/              # (선택) 음성
integrations/         # Hermes 스킬·플러그인, Aloha 등
docs/                 # 도메인·IA·API·음성 설계
obsidian-vault/       # 프로젝트 지식 베이스 (Wiki docs 소스)
requirements.txt
run.bat / run.sh
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
| `[docs/ia/IA.md](docs/ia/IA.md)`                                               | 정보 구조·요청 경로                        |
| `[docs/api/](docs/api/)`                                                       | API 관련 문서                          |
| `[integrations/hermes-skills/README.md](integrations/hermes-skills/README.md)` | Iris Control Surface (Hermes ↔ UI) |


---

## 기여

이슈·PR 환영합니다. 변경 전에는 가능하면 기존 `_check_*.py` 스모크나 관련 모듈 단위 확인을 돌려 주세요.

```powershell
# 예: IDE companion orphan 창 회귀 방지
py -3 -m iris.ui._check_ide_companion_windows
```

---

## 라이선스

루트 `LICENSE` 파일이 아직 없습니다. **오픈소스 대회·공개 저장소 제출 전** OSI 승인 라이선스(예: MIT, Apache-2.0)를 추가하는 것을 권장합니다.  
서드파티(Ollama, Hermes, PyQt6 등)는 각 프로젝트의 라이선스를 따릅니다.

---

## 면책

IRIS는 Hermes 도구를 통해 로컬 파일·터미널에 영향을 줄 수 있습니다.  
중요한 작업 전에는 권한 설정과 확인 다이얼로그를 확인하세요. 프로덕션 자동화·무인 실행은 사용자 책임 하에 진행하세요.