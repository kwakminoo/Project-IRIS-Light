# Iris Light

원본 Iris의 **메인 HUD UI**를 유지한 채, **Ollama(모델) + Hermes Agent(도구·스킬·MCP)** 를 감싸는 Windows 데스크톱 프레임입니다.

이 README만으로 **클론 → 의존성 → Hermes 키 이전 → 실행**까지 재현할 수 있게 작성했습니다.  
AI 에이전트는 아래 **「AI / 자동화 설치 체크리스트」**를 순서대로 실행하면 됩니다.

상세 IA: [docs/ia/IA.md](docs/ia/IA.md) · API: [docs/api/API-명세서.md](docs/api/API-명세서.md)

---

## 아키텍처 (요약)

```
사용자
  └─ Iris Light (PyQt6 HUD)
        ├─ Chat / Wiki / Email / IDE Companion / Monitor
        ├─ Ollama :11434          ← LLM 추론 (로컬·클라우드 프록시)
        └─ Hermes Gateway :8642   ← 도구·스킬·웹검색·iris-control MCP
              ├─ %LOCALAPPDATA%\hermes\.env     ← API 키 (SerpApi 등)
              └─ %LOCALAPPDATA%\hermes\config.yaml
```

Iris 기동 시 자동으로:

1. Control Surface HTTP (`iris_invoke` 등) 기동  
2. Hermes에 `mcp_servers.iris-control` + 스킬 동기화  
3. Gateway를 안전하게 재기동해 MCP 도구 연결 유지  

---

## 요구 사항

| 항목 | 권장 |
|------|------|
| OS | Windows 10/11 (현재 코드는 `pywin32`·IDE 타일링 기준) |
| Python | 3.11+ (`py -3 --version`) |
| Ollama | 설치·실행, 모델 1개 이상 (`ollama list`) |
| Hermes Agent | 설치 후 `hermes` PATH, API Server `:8642` |
| 네트워크 | 최초 클라우드 카탈로그·웹검색 키 검증 시 |

---

## AI / 자동화 설치 체크리스트

아래를 **위에서 아래 순서**로 실행하세요. 이미 끝난 단계는 건너뛰면 됩니다.

### 0) 저장소

```powershell
git clone https://github.com/kwakminoo/Project-IRIS-Light.git
cd Project-IRIS-Light
```

### 1) Python venv + Iris 의존성

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
```

필수 패키지: `PyQt6`, `PyQt6-WebEngine`, `python-dotenv`, `PyYAML`, `psutil`, `mss`, `Pillow`, `markdown`, Windows면 `pywin32`.

### 2) 프로젝트 `.env` 생성

```powershell
copy .env.example .env
```

`.env`의 `IRIS_*` 는 Iris가 직접 읽습니다.  
웹검색 등 **도구 API 키는 Iris가 읽지 않습니다** → Hermes `.env`로 옮겨야 합니다 (다음 단계).

### 3) Hermes 설치 (없는 경우)

```powershell
# 공식 설치 (PowerShell)
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
hermes --version
```

### 4) `.env` 주석 키 → Hermes `.env`로 이전 (중요)

Iris 채팅·웹검색·API Server가 정상 동작하려면 Hermes가 키를 들고 있어야 합니다.

**방법 A — 스크립트 (권장)**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\apply_env_to_hermes.ps1
```

프로젝트 `.env` 또는 `.env.example` 안의 `# SERPAPI_API_KEY=...` 같은 **주석 스냅샷**을  
`%LOCALAPPDATA%\hermes\.env` 에 병합합니다.

**방법 B — 수동**

1. `.env.example` (또는 `.env`) 하단 「Hermes로 옮길 키」주석을 연다.  
2. `# KEY=value` 에서 `# ` 를 제거한 줄을 복사한다.  
3. `%LOCALAPPDATA%\hermes\.env` 에 붙여넣거나 기존 키를 덮어쓴다.  

최소 필수 (Iris ↔ Hermes 채팅):

```env
API_SERVER_ENABLED=true
API_SERVER_KEY=change-me-local-dev
```

웹검색까지 쓰려면 추가로:

```env
SERPAPI_API_KEY=...
SERPAPI_DEFAULT_ENGINE=google
EXA_API_KEY=...
FIRECRAWL_API_KEY=...
```

`IRIS_HERMES_API_KEY`(프로젝트 `.env`) 와 `API_SERVER_KEY`(Hermes `.env`) 와  
`config.yaml` 의 `platforms.api_server.extra.key` 는 **같은 문자열**이어야 합니다.  
기본 스냅샷 값은 `change-me-local-dev` 입니다.

### 5) Hermes config — Ollama + API Server

`%LOCALAPPDATA%\hermes\config.yaml` 에 최소한 다음이 있어야 합니다 (없으면 `hermes setup` 후 수정).

```yaml
model:
  default: gemma4-26b:latest   # ollama list 에 있는 이름
  provider: ollama
  base_url: http://127.0.0.1:11434/v1

platforms:
  api_server:
    enabled: true
    extra:
      key: change-me-local-dev

# 웹검색 백엔드 (SerpApi 플러그인 사용 시)
# web:
#   search_backend: serpapi
# plugins:
#   enabled:
#     - web/serpapi
```

### 6) Ollama

```powershell
# Ollama 앱 실행 후
ollama list
# 없으면 예:
# ollama pull gemma4:26b
```

프로젝트 `.env` 의 `IRIS_OLLAMA_MODEL` 을 `ollama list` 이름과 맞춥니다.

### 7) 실행

```powershell
.\run.bat
# 또는
.\.venv\Scripts\python.exe -m iris
```

첫 기동 시 라이브 로그에 비슷한 문구가 보이면 정상입니다.

- `Iris↔Hermes: MCP iris-control ok`
- `Hermes MCP 재연결 완료` / `iris-control tools ok`
- `Models: N local + M cloud`

### 8) 검증

```powershell
# Hermes API
curl http://127.0.0.1:8642/health

# MCP (Iris 기동 후)
hermes mcp test iris-control
```

Iris 채팅에서 `ide 켜줘` → IDE Companion(사이드바 IDE 아이콘과 동일)이 켜지면 Control 경로 OK.

설정 → **「지금 MCP/스킬 동기화」** 로 수동 재동기화도 가능합니다.

---

## 사람이 읽는 빠른 실행 (이미 환경 있음)

```bat
copy .env.example .env
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\apply_env_to_hermes.ps1
.\.venv\Scripts\pip.exe install -r requirements.txt
.\run.bat
```

---

## `.env` vs Hermes `.env` 역할

| 파일 | 누가 읽나 | 내용 |
|------|-----------|------|
| 프로젝트 `.env` | Iris (`iris.config.settings`) | `IRIS_OLLAMA_*`, `IRIS_HERMES_*` |
| `%LOCALAPPDATA%\hermes\.env` | Hermes Agent | `API_SERVER_*`, `SERPAPI_*`, `EXA_*`, `FIRECRAWL_*` … |
| `.env.example` | 사람/AI용 템플릿 | Iris 활성 키 + Hermes 키 **주석 스냅샷** |

웹검색·SerpApi 잔량 표시는 Hermes `.env` 키를 읽습니다 (`iris/infrastructure/api_quota.py`).

---

## 포함 / 미포함

| 포함 | 미포함 |
|------|--------|
| HUD·채팅·Wiki·이메일·IDE Companion·알림 | Full Iris 자체 오케스트레이터 |
| Ollama 모델 선택·Hermes 도구/MCP | Iris 내부 웹검색 재구현 (Hermes 위임) |
| 분리형 `.venv-voice` 기반 STT/TTS (mock 기본, 설정 UI·답변별 TTS) | 대규모 자동 음성 미세조정 / 클라우드 음성 |
| 기동 시 iris-control MCP 자동 동기화 | Android 에뮬레이터 SDK 자동 설치 |

---

## 트러블슈팅

| 증상 | 확인 |
|------|------|
| 채팅이 안 되고 gateway Offline | `hermes gateway` / Iris 재시작. `API_SERVER_ENABLED=true` |
| `ide 켜줘`가 텍스트만 답함 | Iris 재시작으로 MCP 재연결. `hermes mcp test iris-control` |
| 설정에서 동기화 실패 / yaml | `.venv`에 `PyYAML` 설치 |
| 모델이 예전에 보이던 클라우드가 없음 | 무료 티어만 표시. Pro 모델은 subscription 403으로 제외 |
| 웹검색 실패 | Hermes `.env`의 `SERPAPI_API_KEY` 등 + gateway 재기동 |

구 gateway가 MCP 0 tools로 남는 경우 Iris가 강제 재기동합니다. 수동으로는:

```powershell
hermes gateway stop --all
.\run.bat
```

---

## SerpApi / 문서

- 공통 URL: `https://serpapi.com/search.json?engine=<엔진>`
- 엔진 목록: [obsidian-vault/API문서/SerpAPI/01 - 엔진 카탈로그.md](obsidian-vault/API문서/SerpAPI/01%20-%20엔진%20카탈로그.md)
- Hermes↔Iris MCP: [integrations/hermes-skills/README.md](integrations/hermes-skills/README.md)

---

## 보안 메모

`.env.example` 주석에 **동작 확인용 API 키 스냅샷**이 들어 있을 수 있습니다.  
공개 포크·공유 전에는 본인 키로 교체하고, 노출됐다면 발급처에서 로테이션하세요.  
실제 로컬 비밀은 항상 gitignore된 `.env` 와 `%LOCALAPPDATA%\hermes\.env` 에만 두세요.

## 음성 데이터 주의

상세: [docs/voice.md](docs/voice.md), [docs/voice_architecture.md](docs/voice_architecture.md)

```powershell
.\scripts\setup_voice_runtime.ps1          # mock/스모크
.\scripts\setup_voice_runtime.ps1 -Full    # 실제 모델
```

- 음성 데이터는 로컬(`127.0.0.1:18765`)에서만 처리됩니다.
- 성우 본인의 동의와 사용 권한이 필요합니다.
- 성우 원본 녹음과 생성 모델은 기본적으로 저장소에 포함하지 않습니다.
- 제3자의 목소리를 무단 복제하면 안 됩니다.
- 녹음 폴더 분석: 설정창 또는 `scripts/prepare_voice_dataset.py`
