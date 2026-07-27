# Iris Light

원본 Iris의 **메인 HUD UI**를 유지한 채, **Ollama(모델) + Hermes Agent(도구·스킬)** 를 감싸는 데스크톱 **프레임**입니다.

## 구조 (Information Architecture)

Iris Light IA

```
사용자
  └─ Iris Light (PyQt6 HUD 프레임)
        ├─ Presentation: Chat / Wiki / Email / Monitor …
        ├─ Runtime Gateway: hermes_client · ollama_client
        └─ Local DB: ~/.iris-light/
              │
              ├─► Ollama :11434          ← LLM 추론
              └─► Hermes Gateway :8642   ← 도구·스킬·웹검색
                    └─ SerpApi / Exa / Firecrawl / Skills …
```

상세: [docs/ia/IA.md](docs/ia/IA.md) · API: [docs/api/API-명세서.md](docs/api/API-명세서.md)

## 실행

### 이미 설치된 경우 (권장)

```bat
run.bat
.venv\Scripts\python -m iris
```

`run.bat`은 `.venv\Scripts\python.exe`가 있으면 자동으로 `python -m iris`를 실행합니다.

### 처음 설치하는 경우

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
run.bat
```

### Ollama + Hermes 준비

1. **Ollama** 실행 (`.env`의 `IRIS_OLLAMA_BASE_URL`, 기본 `http://127.0.0.1:11434/v1`)
2. **Hermes gateway** 실행 — Iris가 Hermes를 쓰려면 필요
  ```bat
   hermes gateway
  ```
3. 프로젝트 `.env` 예:
  ```env
   IRIS_HERMES_ENABLED=1
   IRIS_HERMES_BASE_URL=http://127.0.0.1:8642/v1
   IRIS_HERMES_API_KEY=change-me-local-dev
  ```
4. 웹검색 키는 **Hermes** `%LOCALAPPDATA%\hermes\.env`
  (`SERPAPI_API_KEY`, `EXA_API_KEY`, `FIRECRAWL_API_KEY` …)

앱 입력창 **모델 콤보**로 Ollama 클라우드/로컬 모델을 고를 수 있습니다.  
선택 모델은 `~/.iris-light/iris_light.db`에 저장됩니다.

## 포함 / 미포함


| 포함                       | 미포함                          |
| ------------------------ | ---------------------------- |
| HUD·채팅·파형·Wiki·이메일·알림    | Full Iris 자체 오케스트레이터         |
| Ollama 모델 선택·thinking 로그 | Iris 내부 웹검색 재구현 (Hermes에 위임) |
| Hermes 경유 SerpApi/스킬/도구  | STT/TTS(기본 비활성 경로)           |


## SerpApi

- 공통 URL: `https://serpapi.com/search.json?engine=<엔진>`
- Hermes `web.search_backend: serpapi` + 스킬 `serpapi`
- 엔진 목록: [obsidian-vault/API문서/SerpAPI/01 - 엔진 카탈로그.md](obsidian-vault/API문서/SerpAPI/01%20-%20엔진%20카탈로그.md)

