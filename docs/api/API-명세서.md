# Iris Light — API 명세서

> Generated-at: 2026-07-22 · Updated-at: 2026-08-25  
> Scope: Iris Light가 **직접 호출**하거나 **Hermes 경유**로 사용하는 외부·내부 HTTP API  
> Secrets: 키 값은 이 문서에 적지 않음. 위치만 명시.

---

## 1. 문서 목적

이 명세서는 다음을 한곳에 모은다.

- 사용 중인 API / 서비스 목록
- **스타트포인트**(누가 언제 호출을 시작하는지)와 **엔드포인트**(실제 URL·경로)
- 인증·역할·연결 관계
- 환경 변수 위치 (Iris vs Hermes)
- Hermes 스킬 매핑
- 에러·쿼터·운영 메모

---

## 2. 시스템 연결도

```
┌──────────────────────────────┐
│  IRIS (PyQt6 UI)             │
│  .env → IRIS_* (연결·옵션)   │
│  Control :8765 · Voice:18765 │
└───────────┬──────────────────┘
            │ OpenAI-compat chat
            │ Authorization: Bearer IRIS_HERMES_API_KEY
            ▼
┌──────────────────────────────┐
│  Hermes API Server           │
│  http://127.0.0.1:8642       │
│  %LOCALAPPDATA%\hermes\.env  │
└───────┬──────────┬───────────┘
        │          │
        │ LLM      │ Tools / Skills / MCP iris-control
        ▼          ▼
   ┌─────────┐  ┌─────────────────────────────────────┐
   │ Ollama  │  │ Exa / Firecrawl / Naver / (Gemini)  │
   │ :11434  │  │ + terminal / web_search / skills    │
   └─────────┘  └─────────────────────────────────────┘
```

| 구간 | 스타트포인트 | 엔드포인트 |
|------|--------------|------------|
| 사용자 채팅 | Iris `ChatPanel` → `main_window` worker | Hermes `POST /v1/chat/completions` |
| 모델 추론(기본) | Hermes agent | Ollama `POST /v1/chat/completions` (`:11434`) |
| 웹검색(기본) | Hermes `web_search` / `web_extract` | Firecrawl 또는 Exa (키·config에 따라) |
| 네이버 검색 | Hermes 스킬 `naver-search` | `https://openapi.naver.com/v1/search/*` |
| Gemini(옵션) | Hermes `provider: gemini` | Google Generative Language API |

---

## 3. 환경 변수 위치

| 파일 | 역할 |
|------|------|
| 저장소 루트 `.env` | Iris UI ↔ Hermes/Ollama 연결 + Control/Setup/캘린더 등 **옵션** |
| `%LOCALAPPDATA%\hermes\.env` | 도구·프로바이더 **API 키** (Exa, Firecrawl, Google, Naver, API_SERVER_KEY …) |
| `%LOCALAPPDATA%\hermes\config.yaml` | Hermes model provider, `web.search_backend` 등 |

### Iris `.env` (연결·옵션)

| 변수 | 예시 | 설명 |
|------|------|------|
| `IRIS_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama base (`/v1` 유무 모두 허용, 클라이언트 정규화) |
| `IRIS_OLLAMA_MODEL` | (비움) | 기본 모델 — 비우면 앱에서 선택 |
| `IRIS_HERMES_ENABLED` | `1` | Hermes 백엔드 사용 |
| `IRIS_HERMES_BASE_URL` | `http://127.0.0.1:8642` | Hermes API base |
| `IRIS_HERMES_API_KEY` | (위저드 생성) | Hermes `API_SERVER_KEY`와 동일 |
| `IRIS_HERMES_COMMAND` | (위저드) | CLI 명령 |
| `IRIS_CONTROL_ENABLED` / `HOST` / `PORT` / `TOKEN` | `8765` | Control Surface |
| `IRIS_DATA_GO_KR_SERVICE_KEY` | — | 공휴일(캘린더) |
| `IRIS_SETUP_DEMO` / `DRY_RUN` | — | 시작 프로토콜 데모/드라이런 |
| `VOICE_RUNTIME_MOCK` | `0`/`1` | 음성 런타임 mock (앱 prefs와 함께 봄) |

### Hermes `.env` (키)

| 변수 | 서비스 |
|------|--------|
| `API_SERVER_ENABLED` / `API_SERVER_KEY` | Hermes API Server |
| `EXA_API_KEY` | Exa |
| `FIRECRAWL_API_KEY` | Firecrawl |
| `GOOGLE_API_KEY` | Google AI Studio (Gemini LLM) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 검색 Open API |

키 변경 후 **`hermes gateway` 재시작** 필요.

---

## 4. API 카탈로그

### 4.1 Hermes API Server (Iris ↔ Hermes)

| 항목 | 내용 |
|------|------|
| **역할** | Iris 채팅·도구 실행의 런타임 게이트웨이 (OpenAI 호환) |
| **연결** | `iris/infrastructure/hermes_client.py` ← `IRIS_HERMES_*` |
| **Base URL** | `http://127.0.0.1:8642` (Iris는 `/v1` suffix 사용) |
| **인증** | `Authorization: Bearer <API_SERVER_KEY>` |
| **스타트포인트** | 사용자 메시지 전송, 모델 동기화, health 체크 |
| **Hermes 스킬** | (서버 자체; 스킬은 서버 *안*에서 로드) |

#### 엔드포인트

| Method | Path | 기능 |
|--------|------|------|
| `GET` | `/health` | 게이트웨이 생존 확인 |
| `POST` | `/v1/chat/completions` | 채팅(스트리밍 SSE 가능). Iris 주 경로 |
| `POST` | `/v1/responses` | Responses API (서버측 상태) |

#### 요청/응답 (chat)

- Request: OpenAI Chat Completions JSON (`model`, `messages`, `stream`)
- Response: completion 또는 SSE (`data: …`). Hermes 확장 이벤트 예: `hermes.tool.progress`
- Error: gateway offline → Iris가 연결 실패 안내

#### 관련 코드

- `iris/infrastructure/hermes_client.py` — `health_ok`, `stream_chat`, `set_inference_model`
- `iris/ui/workers/hermes_workers.py` / `main_window.py` — UI 워커

---

### 4.2 Ollama (로컬·클라우드 모델)

| 항목 | 내용 |
|------|------|
| **역할** | LLM 추론 (Hermes `provider: custom`의 기본 백엔드). Iris 모델 목록·설명 UI |
| **연결** | Hermes → `http://127.0.0.1:11434/v1`; Iris 직접 목록은 `iris/infrastructure/ollama_client.py` |
| **Base URL** | `http://127.0.0.1:11434` |
| **인증** | 로컬 기본 없음. Ollama Cloud 사용 시 `OLLAMA_API_KEY` (Hermes) |
| **스타트포인트** | 채팅 완료 요청, `/api/tags`, `/api/show` (모델 메타·tools 필터) |

#### 엔드포인트

| Method | Path | 기능 |
|--------|------|------|
| `POST` | `/v1/chat/completions` | OpenAI 호환 채팅 (Hermes/Iris) |
| `GET` | `/api/tags` | 로컬 모델 목록 |
| `POST` | `/api/show` | capabilities·파라미터 (tools 필터에 사용) |
| `POST` | `/api/chat` | 네이티브 채팅 스트림 |
| (외부) | `https://ollama.com/api/tags` | 클라우드 카탈로그 (Iris 목록용) |

#### 관련 코드

- `iris/infrastructure/ollama_client.py`
- `iris/infrastructure/model_descriptions.py` — UI 모델 설명
- `iris/ui/ollama_workers.py`

---

### 4.3 Exa

| 항목 | 내용 |
|------|------|
| **역할** | AI형 웹 검색·페이지 contents 추출 |
| **연결** | Hermes 빌트인 `web_search` / `web_extract` **또는** 스킬 `exa` + terminal |
| **Base URL** | `https://api.exa.ai` |
| **인증** | Header `x-api-key: $EXA_API_KEY` |
| **스타트포인트** | 사용자가 웹조사/검색을 요청하고 백엔드가 Exa일 때 |
| **Hermes 스킬** | `%LOCALAPPDATA%\hermes\skills\iris-apis\exa\SKILL.md` (`name: exa`) |

#### 엔드포인트

| Method | Path | 기능 |
|--------|------|------|
| `POST` | `/search` | 검색 |
| `POST` | `/contents` | URL/ID 기준 본문 추출 |

#### 운영

- 대시보드에서 **Auto recharge OFF** 권장 (추가결제 방지)
- HTTP `402` — 크레딧/예산 소진
- Firecrawl 키가 같이 있으면 Hermes 자동선택은 **Firecrawl 우선** → Exa 고정 시:

```yaml
# ~/.hermes/config.yaml
web:
  search_backend: "exa"
  extract_backend: "exa"
```

---

### 4.4 Firecrawl

| 항목 | 내용 |
|------|------|
| **역할** | 웹 검색·스크rape·크롤 (Hermes 기본 웹 백엔드 후보) |
| **연결** | Hermes `web_*` **또는** 스킬 `firecrawl` + terminal |
| **Base URL** | `https://api.firecrawl.dev` (v1/v2 계정에 따름) |
| **인증** | `Authorization: Bearer $FIRECRAWL_API_KEY` |
| **스타트포인트** | 웹검색/페이지추출/사이트 크롤 요청 |
| **Hermes 스킬** | `…\skills\iris-apis\firecrawl\SKILL.md` (`name: firecrawl`) |

#### 엔드포인트

| Method | Path | 기능 |
|--------|------|------|
| `POST` | `/v1/search` | 검색 |
| `POST` | `/v1/scrape` | 단일 URL 추출 |
| `POST` | `/v1/crawl` | 멀티 페이지 크롤 (`limit` 필수 권장) |
| `GET` | `/v1/team/credit-usage` | 잔여 크레딧 조회 |

#### 운영

- **Smart Upgrade OFF** 권장
- Crawl 시 `limit` 미지정 시 사전 크레딧 검사로 402 날 수 있음
- HTTP `402` — 크레딧 소진

---

### 4.5 SerpApi (멀티 엔진 SERP)

| 항목 | 내용 |
|------|------|
| **역할** | Google/Bing/Yahoo/News/Images/Shopping/Maps/YouTube/Amazon/Naver 등 **엔진별 검색 결과 JSON** |
| **연결** | Hermes 빌트인 `web_search` (`search_backend: serpapi`) + 스킬 `serpapi` |
| **Base URL** | `https://serpapi.com/search.json` |
| **인증** | 쿼리 `api_key=$SERPAPI_API_KEY` |
| **스타트포인트** | Iris 채팅 → Hermes tool-call `web_search` 또는 스킬 스크립트 |
| **엔진 전환** | **동일 엔드포인트** + `engine=<이름>` (엔진마다 URL을 따로 연결할 필요 없음) |
| **Hermes 플러그인** | `plugins/web/serpapi` (소스: `integrations/hermes-plugins/web/serpapi/`) |
| **Hermes 스킬** | `%LOCALAPPDATA%\hermes\skills\iris-apis\serpapi\` |
| **Iris 참고 클라이언트** | `iris/infrastructure/serpapi_client.py` |

#### 엔드포인트

| Method | Path | 기능 |
|--------|------|------|
| `GET` | `/search.json?engine=google&q=…` | Google 웹 (기본) |
| `GET` | `/search.json?engine=<ENGINE>&…` | 엔진별 검색 (images/news/bing/yahoo_images/…) |

주요 `engine` 값: `google`, `google_news`, `google_images`, `google_maps`, `bing`, `yahoo_images`, `youtube`, `amazon`, `naver` …  
전체: Wiki `API문서/SerpAPI/01 - 엔진 카탈로그.md`

#### 설정

```yaml
# ~/.hermes/config.yaml
web:
  search_backend: "serpapi"
  extract_backend: "firecrawl"   # SerpApi는 extract 미지원
```

```env
SERPAPI_API_KEY=...
SERPAPI_DEFAULT_ENGINE=google
```

#### 운영

- Free plan 검색 횟수 제한(대시보드) — 소진 시 에러
- `web_extract`는 Firecrawl/Exa 유지

---

### 4.6 Google AI Studio (Gemini) — `GOOGLE_API_KEY`

| 항목 | 내용 |
|------|------|
| **역할** | **LLM(Gemini)** 추론. 웹검색 API가 **아님** |
| **연결** | Hermes `model.provider: gemini` 일 때만 채팅 경로에 사용. 기본(Ollama custom)에서는 미사용 |
| **Base URL** | OpenAI 호환: `https://generativelanguage.googleapis.com/v1beta/openai` |
| **인증** | `Authorization: Bearer $GOOGLE_API_KEY` (호환 엔드포인트) |
| **스타트포인트** | provider를 gemini로 바꾼 뒤의 채팅 / 스킬 직접 호출 |
| **Hermes 스킬** | `…\skills\iris-apis\google-gemini\SKILL.md` (`name: google-gemini`) |

#### 엔드포인트

| Method | Path | 기능 |
|--------|------|------|
| `POST` | `/v1beta/openai/chat/completions` | OpenAI 호환 채팅 |
| `POST` | `/v1beta/models/{model}:generateContent` | 네이티브 생성 |

#### 주의

- Google **Custom Search / Maps** 와 키·콘솔이 다름
- 무료 할당량 소진 시 호출 거부 (Iris에 잔액 UI 없음)

---

### 4.7 Naver Search Open API

| 항목 | 내용 |
|------|------|
| **역할** | 네이버 웹문서·뉴스·블로그·쇼핑·지역 등 **한국 포털 검색** |
| **연결** | Hermes 스킬 `naver-search` → terminal/python (빌트인 web_search에 네이버 없음) |
| **Base URL** | `https://openapi.naver.com` |
| **인증** | `X-Naver-Client-Id`, `X-Naver-Client-Secret` |
| **스타트포인트** | “네이버에서 … 검색” 등 → 스킬 로드 → 스크립트/curl |
| **Hermes 스킬** | `…\skills\iris-apis\naver-search\SKILL.md` + `scripts/naver_search.py` |
| **발급** | https://developers.naver.com — 비로그인 검색, PC웹 + `http://localhost` |

#### 엔드포인트

| Method | Path | 기능 |
|--------|------|------|
| `GET` | `/v1/search/webkr.json` | 웹문서 |
| `GET` | `/v1/search/news.json` | 뉴스 |
| `GET` | `/v1/search/blog.json` | 블로그 |
| `GET` | `/v1/search/shop.json` | 쇼핑 |
| `GET` | `/v1/search/local.json` | 지역 |
| `GET` | `/v1/search/image.json` | 이미지 |
| `GET` | `/v1/search/kin.json` | 지식iN |
| `GET` | `/v1/search/book.json` | 책 |
| `GET` | `/v1/search/encyc.json` | 백과 |
| `GET` | `/v1/search/cafearticle.json` | 카페글 |
| `GET` | `/v1/search/doc.json` | 전문자료 |

공통 쿼리: `query` (필수), `display` (1–100), `start`, `sort`(API별)

#### 스크립트

```text
%LOCALAPPDATA%\hermes\skills\iris-apis\naver-search\scripts\naver_search.py
  <kind> <query> [display]
```

#### 범위 밖

- **네이버 지도 / Directions / Geocoding** → NCP(AI·NAVER Maps) 별도 Application. 현재 Iris/Hermes 키셋에 미포함.

---

## 5. Hermes 스킬 등록 목록 (Iris APIs)

| Skill `name` | 경로 | 대응 API |
|--------------|------|----------|
| `exa` | `skills/iris-apis/exa/` | Exa |
| `firecrawl` | `skills/iris-apis/firecrawl/` | Firecrawl |
| `serpapi` | `skills/iris-apis/serpapi/` | SerpApi (engine=) |
| `google-gemini` | `skills/iris-apis/google-gemini/` | Google AI Studio |
| `naver-search` | `skills/iris-apis/naver-search/` | Naver Search |

루트: `%LOCALAPPDATA%\hermes\skills\iris-apis\`

스킬은 게이트웨이 재시작(또는 Hermes 스킬 리로드) 후 `skills_list` / 자연어 트리거로 로드된다.  
Exa·Firecrawl은 **빌트인 `web_search`가 1차**, 스킬은 백엔드 고정·직접 REST·운영 가이드용.

---

## 6. 호출 흐름 요약 (스타트 → 엔드)

| # | 사용자 의도 | 스타트포인트 | 중간 | 엔드포인트 |
|---|-------------|--------------|------|------------|
| 1 | 일반 대화 | Iris Send | Hermes Agent | Ollama `/v1/chat/completions` |
| 2 | 웹 조사 | Iris Send | Hermes `web_search` | Firecrawl 또는 Exa API |
| 3 | URL 본문 | Iris Send | Hermes `web_extract` | Firecrawl/Exa contents/scrape |
| 4 | 네이버 뉴스/검색 | Iris Send | skill `naver-search` | `openapi.naver.com/v1/search/*` |
| 4b | 웹/뉴스/이미지(SerpApi) | Iris Send | `web_search` / skill `serpapi` | `serpapi.com/search.json?engine=` |
| 5 | Gemini로 바꾸기 | config provider | Hermes | Google Generative Language |
| 6 | 모델 목록/설명 | Iris 부팅·콤보 | `ollama_client` | Ollama `/api/*` + ollama.com catalog |

---

## 6b. Iris Control Surface (Hermes → Iris 역제어)

Hermes가 Iris UI를 조작하는 **로컬 제어면**. 키워드 라우터 없음 — Hermes tool-calling만.

```
Hermes MCP iris-control (stdio)
  → HTTP 127.0.0.1:8765
    → MainWindow 핸들러 (IDE Companion, workspace, settings, …)
```

| Method | Path | 설명 |
|--------|------|------|
| GET | `/v1/state` | 세션 상태 |
| GET | `/v1/catalog` | 액션 목록 |
| GET | `/health` · `/v1/ping` | 생존 |
| POST | `/v1/invoke` | `{ "action", "args" }` |

인증: `Authorization: Bearer <IRIS_CONTROL_TOKEN>` (또는 `~/.iris-light/control_token`)

MCP 도구: `iris_get_state`, `iris_get_catalog`, `iris_invoke`  
설치·스킬: `integrations/hermes-skills/README.md`  
**자동 동기화:** Iris 기동 시 `hermes_iris_control_sync`가 Hermes `config.yaml`·skills·MEMORY에 기록(재시작 유지). 변경 시 gateway `--replace`.

대표 액션: `ide.enter_companion`, `ide.exit_companion`, `ide.open_folder`, `ide.open_file`, `project.write_file` (`open`/`stream`), `project.run`, `workspace.open_*`, `profile.set`, `email.*`, `wiki.*`, `settings.*`  
고위험(`email.send` 등)은 `args.confirm=true` 필수.

바이브코딩: `project.write_file`(기본 open+live stream)로 IDE 탭을 열고 파일 내용을 청크로 늘리며, 실행은 `project.run`이 **IDE 통합 터미널**에 출력(로그 파일 탭 아님). 채팅은 `summary`만.

---

## 7. 공통 에러·운영

| 증상 | 원인 | 조치 |
|------|------|------|
| Iris HERMES Offline | gateway 미실행 | `hermes gateway` |
| 웹검색 안 됨 | 키 없음 / tools 미지원 모델 | Hermes `.env` + tools 모델 |
| 네이버 401/403 | 키·권한 | 개발자센터 앱·검색 API ON |
| Exa/Firecrawl 402 | 크레딧 소진 | 대시보드, auto-upgrade/recharge OFF |
| 키가 Iris에만 있음 | Hermes가 안 읽음 | `%LOCALAPPDATA%\hermes\.env`로 이동 |

---

## 8. 보안

- API 키를 git에 커밋하지 말 것 (`.env`는 로컬 전용)
- Iris `.env`와 Hermes `.env` 역할 분리 유지
- Client Secret / API Key는 UI·위키·채팅에 붙여넣지 말 것

---

## 9. 관련 문서

- `docs/domain.md` — 도메인·바운디드 컨텍스트
- Wiki: [[프로젝트 개요]] · [[05 - API Server와 Iris Light 연동]] · [[03 - 클라우드 모델 카탈로그]]
- Hermes web: https://hermes-agent.nousresearch.com/docs/user-guide/features/web-search
- Naver: https://developers.naver.com/docs/common/openapiguide/appregister.md
- Exa: https://docs.exa.ai · Firecrawl: https://docs.firecrawl.dev
- Google AI Studio: https://aistudio.google.com

---

## 10. 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-08-25 | 현황 동기화: env 표 확장, Control/Voice 포트, 워커 경로, 모델 예시 비움 |
| 2026-07-22 | 초판. Hermes/Ollama/Exa/Firecrawl/Google/Naver + iris-apis 스킬 매핑 |
| 2026-07-22 | SerpApi 플러그인·engine 카탈로그·IA 문서 추가 |
| 2026-07-24 | Iris Control Surface + Hermes MCP iris-control + work-start 스킬 |
