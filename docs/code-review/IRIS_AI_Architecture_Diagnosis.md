# IRIS AI Architecture Diagnosis

> **문서 성격:** 구현 금지 · 코드·기획 대조 기반 구조 진단  
> **대상 저장소:** Project-IRIS-Light  
> **진단일:** 2026-09-22  
> **재확인:** 2026-09-23 (기획·코드 재대조 · 개선 예정 총괄표 신설)  
> **분석 수단:** code-review-graph · 소스 · `docs/code-review/조치-소요-사항-총괄표.md`  

---

## 총괄. 개선 예정 사항 요약표

본 표는 진단 본문(§1~§9)을 **실제 구조·기획과 재확인**한 뒤, 아직 개선이 필요한 사항만 정리한 것이다.  
「Hermes를 켜는 것」은 이미 설계상 필수(2026-09-17)이므로 **재실시 대상이 아니다.**  
런타임 추론 모델은 피커·DB 선택값이며, 설치용 최소 모델(`gemma4:e2b`)과 **동일시하지 아니한다.**

| 연번 | 문제 | 원인 | 발생 상황 | 근거 | 개선방향 |
|:---:|:---|:---|:---|:---|:---|
| 1 | Wiki·코드·문서 근거 없이 답함 (환각·재질문) | 지식은 파일로 저장되나 LLM 컨텍스트에 **자동 회수(RAG) 없음** | 프로젝트·위키·첨부 이력을 묻는 질문, 바이브코딩 설명 | `iris/knowledge/*`는 list/read 수준. chromadb/faiss 등 벡터 파이프라인 미검출. SOUL는 「개인형 AI 비서」 표방 | Wiki/코드 **경량 RAG**(chunk·embedding·top-k) MVP |
| 2 | 세션 밖·장기 선호를 기억하지 못함 | `_history`는 프로세스 메모리. Hermes `MEMORY.md`는 **도구 사용 nudge** 수준 | 재기동 후, 또는 긴 대화에서 과거 결정·선호 재질문 | `main_window` `_history`, `hermes_memory_nudge.py` | 세션 요약 저장 + 사용자/프로젝트 **Memory retrieve** |
| 3 | 도구·지시 준수율이 들쭉날쭉함 | 매 턴 system에 **긴 MCP 매뉴얼 덤프**. 작은 모델·혼잡 컨텍스트에서 지시 무시 용이 | Agent·MCP 작업(IDE/메일/위키) 시, 컨텍스트가 긴 턴 | `_chat_messages_with_project_context` | 지시 축소 + Memory/File/Web/Code **MCP 역할 분리**(필요 시 도구로만 조회) |
| 4 | Hermes·도구 품질을 수치로 관리하지 못함 | 경로 고정은 완료됐으나 **성공률·실패 모드 계측 부재**. gateway Offline 시 체감 급락 | Hermes gateway 기동 실패·도구 오호출·빈 응답 | 총괄표 §3 바(Hermes 필수 확정). `_check_hermes_required`. `_hermes_online` 가드 | **도구 호출 성공률·citation·재질문률 계측** + Offline 경보 SLA |
| 5 | 소형 로컬만 쓸 때 Agent 품질 부족 | 설치 게이트 기본이 `gemma4:e2b`(초소형). Agent+MCP+한국어에 용량 부족 가능 | **피커가 비었거나 최소 로컬을 고른 경우**. (클라우드/API 선택 시 본 항은 주원인이 아님) | `setup_protocol.DEFAULT_MIN_MODEL`, `load_selected_model`, `resolve_hermes_inference` | **모델 티어 정책**(회화 소형 / Agent 중형·클라우드). 벤치 후 기본 권장만 조정 |
| 6 | 단순 요청에도 무거운 Agent 경로 | Iris에 **의도 라우터 없음**. 규칙 숏컷 외는 대부분 Hermes에 위임 | IDE 전환·위키 저장 등 이미 로컬 가능한 요청이 LLM으로 감 | `runtime/voice_intents`, MainWindow 로컬 숏컷 vs `_execute_user_turn` | Iris 측 **Intent Router**(숏컷 / 검색 / Hermes) 명시 |
| 7 | 메일·캘린더·메인챗 맥락이 단절됨 | 도메인별 하드코딩 프롬프트·패널. 공유 Memory/RAG 없음 | 워크스페이스 전환 후 이전 맥락 재설명 | `email_client` / calendar 경로, `_chat_messages_with_project_context` | 공통 Memory·프로젝트 컨텍스트 훅으로 **경로 정합** |
| 8 | 복잡한 다단계 작업이 한 에이전트에 몰림 | Iris 코어에 multi-agent/Planner 모듈 없음(기획상 Hermes 위임) | 조사+코딩+일정 등 복합 요청 | `assistant/external_agent_adapter.py`는 상태 표시용. Level 2~3 하이브리드 | (중기) 역할 분리 Multi Agent. (단기) Router+RAG로 충분 여부 먼저 검증 |
| 9 | 로컬 대형·초장문 차별화 미정 | 제품 기본은 소형 설치 + 클라우드/API·Hermes 조합 | VRAM·오프라인 고품질이 필요할 때 | 설치 프로토콜·Ollama 중심 설계 | **연구 과제**(Large Model / Kimi 등). 제품 기본값 변경 전제 아님 |

### 재확인 결과 — 개선 예정에서 제외(또는 등급 하향)

| 항 | 당초 진단 표현 | 재확인 | 조치 |
|:---|:---|:---|:---|
| A | 「Hermes ON 고정」을 1순위 개선으로 제시 | **이미 완료.** UI/설정/컨트롤로 끄기 불가. 클라우드·API도 Hermes `custom`으로 수용 | 재고정 불요. 잔여: env `IRIS_HERMES_ENABLED=0`(개발용) · **계측**만 예정(연번 4) |
| B | 「모델 자체 성능 부족(높음)」·기본 `gemma4:e2b`가 일상 품질 주원인 | **설치 최소 모델 ≠ 런타임 선택 모델.** 기획·실사용은 클라우드/API+Hermes가 주경로 | 연번 5는 **조건부**. 클라우드 사용 시 RAG/Memory/프롬프트(연번 1~3)가 우선 |
| C | 「Hermes OFF 시 Level 1 급락」을 TOP 문제화 | 일반 사용자 경로에서는 발현되지 않음 | 문서상 잔여 분기로만 유지. 제품 개선 순위 제외 |

### 권장 착수 순서 (구현 시)

1. 연번 **4**(계측) → 2. 연번 **2**(Memory MVP) → 3. 연번 **1**(Wiki RAG MVP) → 4. 연번 **3·6**(프롬프트·Router) → 5. 연번 **5**(티어, 벤치 후) → 6. 연번 **7~9**(중기·연구)

> 원칙: 모델 교체만으로 해결하려 하지 말 것. 병목은 **회수(RAG/Memory) + 지시·도구 경로의 일관성·관측**이다.

---

## 0. 진단 범위와 방법

| 항목 | 내용 |
|------|------|
| 허용 | 코드 읽기, 그래프 탐색, 문서 작성 |
| 금지 | 코드 수정, 기능 구현, MCP/RAG 구축, 의존성 설치, 리팩토링 |
| 그래프 근거 | communities: `audio-voice`, `infrastructure-model`, `runtime-intent`, `knowledge-wiki`, `mcp-tool` / flow: `_dispatch_user_turn` (229 nodes) |

---

## 1. 프로젝트 전체 구조 분석

### 1.1 아키텍처 한 줄 정의

IRIS Light는 **웹 Frontend/Backend 분리 서비스가 아니라**, Windows 중심 **PyQt6 데스크톱 셸**이다.  
LLM·도구·음성은 로컬 프로세스(Ollama / Hermes gateway / voice_runtime)와 HTTP로 연결된다.

### 1.2 상위 폴더 역할

| 경로 | 역할 |
|------|------|
| `iris/` | 앱 본체 (UI·런타임·인프라·지식·MCP) |
| `services/voice_runtime/` | 별도 STT/TTS FastAPI 런타임 (`.venv-voice`) |
| `integrations/hermes-soul/` | Hermes 페르소나 `SOUL.md` 원본 |
| `dist/IRIS.exe` | thin launcher → `.venv\Scripts\pythonw.exe -m iris` |
| `docs/` | IA·음성·API·코드리뷰 문서 |
| `tests/` | 단위/계약 테스트 |
| `scripts/` | 빌드·voice setup·exe 등 |
| `obsidian-vault/` | 학습/노트 자산 (앱 RAG 아님) |

### 1.3 `iris/` 모듈 맵

| 모듈 | 역할 |
|------|------|
| `ui/` | Frontend: MainWindow, ChatPanel, 워크스페이스(IDE/메일/캘린더), 설정 |
| `infrastructure/` | LLM 클라이언트 (Hermes / Ollama / OpenAI-compat), SerpAPI, Firecrawl, 이메일 |
| `audio/` | 마이크·VAD·STT 큐·TTS 펌프·voice_runtime 클라이언트 |
| `runtime/` | UserTurn 큐, 음성 규칙 인텐트 |
| `system/` | Ollama/Hermes 기동, IDE 타일, setup, control surface |
| `mcp/` | Iris Control MCP stdio 서버 (`iris_get_state/catalog/invoke`) |
| `knowledge/` | Wiki/Obsidian/코드 인덱스/콘텐츠 추출 (파일 기반, 비벡터) |
| `storage/` | SQLite DB, 프로필, 음성 설정, API provider |
| `learning/` | 화면 조작 학습(ALOHA), elevation |
| `assistant/` | 백엔드 상태 표시 어댑터 (에이전트 코어 아님) |
| `config/` | Settings (모델·URL) |
| `core/` | 마크다운/채팅 블록 파싱 |

### 1.4 Frontend / Backend 구분 (실제)

| 계층 | 구현 | 비고 |
|------|------|------|
| Frontend | PyQt6 (`iris/ui/**`) | SPA 없음 |
| App Backend | MainWindow 오케스트레이션 + control HTTP | 별도 API 서버 앱이 메인 아님 |
| Inference Backend | Ollama (`/api/chat`) · Hermes (`/v1/chat/completions`) · OpenAI-compat | 로컬/클라우드 혼재 |
| Voice Backend | `services.voice_runtime.app` | 별 프로세스 |
| Tool Backend | Hermes Agent + MCP `iris_control` | UI 제어·프로젝트 액션 |

### 1.5 Entry Point

```
dist/IRIS.exe (thin launcher)
    ↓
.venv\Scripts\pythonw.exe -m iris
    ↓
iris/__main__.py::main()
    ↓
iris.ui.qt_bootstrap → MainWindow
```

근거: `iris/__main__.py`, 워크스페이스 규칙 `iris-exe-latest-build.mdc`.

### 1.6 실제 데이터/API 흐름 (코드 기준)

키보드·첨부 경로와 음성 경로를 합친 **현재 실제 파이프라인**:

```
사용자 입력 (키보드 / 마이크 / 파일 드롭 / 워크스페이스 챗)
        ↓
입력 처리
  · UserTurnDispatcher.submit → MainWindow._dispatch_user_turn
  · 로컬 숏컷: IDE 제어 / Wiki 저장 / 워크스페이스 전환
  · 음성 특수 인텐트: voice_intents (전화/알림 — LLM 우회)
        ↓
STT (음성일 때만)
  · MicrophoneController + Silero VAD → WAV utterance
  · SttJobQueue → VoiceRuntimeClient.transcribe_* 
  · services/voice_runtime: faster-whisper (default model "small", language=ko)
        ↓
LLM 호출
  · messages = _chat_messages_with_project_context()
      (system: MCP 지침 + project_root [+ Ollama 직행 시 SOUL])
      + in-memory _history
  · Hermes ON → HermesChatWorker → Hermes /v1/chat/completions (도구·MCP 가능)
  · Hermes OFF + API 모델 → OpenAI-compat stream
  · Hermes OFF + Ollama 모델 → OllamaChatWorker → /api/chat
        ↓
응답 처리
  · content_chunk → ChatPanel 스트림 렌더
  · tool_progress → 도구 진행 UI
  · 코드블록 감지 시 vibe/IDE companion 연출
  · assistant 메시지를 _history에 append
        ↓
TTS (자동 음성 응답 모드일 때)
  · TtsSentencePump로 문장 단위 절단
  · TTSStreamWorker → VoiceRuntime Qwen3-TTS 스트림
  · PcmPlayer 재생 (+ AEC far-end)
        ↓
사용자 출력 (채팅 UI + 스피커)
```

핵심 오케스트레이션 근거:

- `MainWindow._execute_user_turn` (`iris/ui/window/main_window.py`)
- `_chat_messages_with_project_context`
- flow `_dispatch_user_turn` (HermesChatWorker / OllamaChatWorker / TTSStreamWorker 포함)

---

## 2. 현재 AI Pipeline 분석

### 2.1 STT

| 항목 | 현재 상태 | 코드 근거 |
|------|-----------|-----------|
| 사용 모델 | **faster-whisper**, 기본명 `"small"` | `services/voice_runtime/stt_service.py` (`WhisperModel`, `model_name="small"`) |
| 실행 방식 | 별도 voice runtime HTTP 서비스 + Qt 워커 | `VoiceRuntimeProcessManager` → `python -m services.voice_runtime.app` |
| 입력 처리 | 연속 마이크 → Silero VAD → utterance WAV → STT 큐 | `iris/audio/recorder.py`, `silero_vad.py`, `stt_queue.py` |
| 언어 | 기본 `ko`, CUDA면 float16 / 아니면 int8 | `stt_service.transcribe_audio` |
| 개선 가능성 | medium↑/large-v3, 스트리밍 STT, 도메인 핫워드, 모델 상주 웜업 강화 | 구조는 이미 warmup/큐 존재 |

**지연 요소:** 모델 콜드 로드, utterance 종료 대기(VAD), WAV 업로드, beam_size=5 디코드.

### 2.2 LLM

| 항목 | 현재 상태 | 코드 근거 |
|------|-----------|-----------|
| 기본 설치 모델 | **`gemma4:e2b`** (로컬), 클라우드 stub **`gemma4:e2b-cloud`** | `setup_protocol.py` `DEFAULT_MIN_MODEL` / `DEFAULT_CLOUD_MODEL` |
| Fallback | Ollama tags 첫 모델, 없으면 **`llama3.2`** | `hermes_gateway._fallback_ollama_model_name` |
| 선택 UI | Ollama 목록 + API provider 모델 피커 | `model_picker_menu.py` |
| Ollama 사용 | **예** (핵심 로컬 런타임) | `ollama_client.py` `/api/chat` NDJSON stream |
| Hermes 사용 | **예** (권장 Agent 경로) | `hermes_client.stream_chat` → `/v1/chat/completions` SSE |
| API 호출 | OpenAI-compat (`openai_compat_client`) | Hermes OFF + `api:` 런타임 시 |
| Local / Cloud | 혼재: 로컬 Ollama + Ollama cloud + 외부 API | setup/usage 모듈 |
| Prompt 관리 | ① Hermes `SOUL.md` identity ② MainWindow system MCP 지침 ③ 도메인별 하드코딩 시스템 프롬프트(메일/캘린더) | `hermes_soul_sync.py`, `_chat_messages_with_project_context`, `email_client`/`calendar_agent` |
| Context 전달 | session `_history` 전체 + project_root + 긴 MCP 사용법 문자열 | 토큰 추정: `estimate_messages_tokens` |
| Conversation | 프로세스 메모리 리스트. Hermes `MEMORY.md`는 도구 사용 **nudging**용 | `hermes_memory_nudge.py` |

**중요 분기 (기획·코드 재확인):**

```
Hermes enabled (제품 기본·UI로 끌 수 없음)
  → 모든 선택 모델(Ollama/클라우드/API)을 Hermes Agent로 라우팅 (MCP 도구 유지)
IRIS_HERMES_ENABLED=0 (개발 우회만)
  → API면 직행 / Ollama면 직행 (도구 없음) — 제품 개선 대상으로 보지 않음
```

근거: `_execute_user_turn`, `docs/code-review/조치-소요-사항-총괄표.md` §3 바, `iris/ui/_check_hermes_required.py`.
런타임 모델은 `load_selected_model` / 피커. `gemma4:e2b`는 **설치 최소**이지 일상 기본 추론 모델이 아님.

### 2.3 TTS

| 항목 | 현재 상태 | 코드 근거 |
|------|-----------|-----------|
| 사용 모델 | **`Qwen/Qwen3-TTS-12Hz-0.6B-Base`** | `voice_runtime_client.py`, `tts_stream.py` `DEFAULT_TTS_MODEL` |
| 실행 방식 | voice runtime HTTP 스트림 + `TTSStreamWorker` | `workers.py`, `iter_tts_speech_stream` |
| 파이프라인 | LLM 스트림 → `TtsSentencePump` → 문장 합성 → PCM 재생 | `tts_pipeline.py`, `pcm_player.py` |
| 부가 | 보이스 클로닝/x-vector, pitch shift, AEC | `voice_profile`, `aec.py` |

**응답 지연 요소:**

1. LLM 첫 토큰 대기  
2. 문장 경계까지 TTS 대기 (`TtsSentencePump`)  
3. TTS 모델 로드/웜업  
4. GPU 경합 (LLM Ollama + Whisper + Qwen-TTS 동시)

---

## 3. 현재 LLM 성능 한계 원인 분석

답변 품질이 낮을 때 **코드·기획으로 뒷받침되는** 원인표.  
(2026-09-23 재확인: 일상 경로 = **Hermes 필수 + 피커 선택 모델(클라우드/API 포함)**.)

| 원인 | 가능성 | 근거 |
|------|--------|------|
| 모델 자체 성능 부족 | **조건부(중~낮)** | 설치 최소는 `gemma4:e2b`이나, 런타임은 `load_selected_model`·클라우드/API가 주경로. **소형 로컬을 고른 경우에만 높음.** |
| Prompt 설계 부족 | **중간~높음** | SOUL는 페르소나에 강함. 반면 매 턴 system에 **긴 MCP 매뉴얼**을 붙여 지시 과다·토큰 소모. Hermes 경로에서는 SOUL를 앱이 중복 주입하지 않음(의도적). |
| Context 부족 | **높음** | `_history`는 대화 롤만. Wiki/코드/파일은 자동 retrieval 없음. `project_root` 문자열만 추가. |
| Memory 부족 | **높음** | 장기 기억은 Hermes `MEMORY.md` nudge(도구 사용법) 수준. 사용자 선호·과거 결정의 구조화 메모리/검색 없음. 앱 `_history`는 세션/프로세스 범위. |
| RAG 부재 | **매우 높음** | `chromadb`/`faiss`/문서 embedding 파이프라인 없음. Wiki는 list/read/write 파일 API. |
| Agent 구조 부족 | **중간(Iris 코어 기준)** | **기획상** Agent는 Hermes에 위임(필수). Iris 자체 Planner는 없음 — 결함이 아니라 역할 분담. Router 부재는 별도 개선(총괄 연번 6). |
| Tool 사용 불가능 | **낮음(정상 경로)** | Hermes+MCP에서 도구 가능. UI로 Hermes OFF 불가. `IRIS_HERMES_ENABLED=0` 개발 우회 시에만 Level 1. 잔여 이슈는 **도구 성공률·Offline**(총괄 연번 4). |

### 3.1 구조적 병목 (품질뿐 아니라 체감)

| 병목 | 설명 |
|------|------|
| 이중 런타임 | UI 프로세스 + Hermes + Ollama + voice_runtime — 실패 모드·콜드스타트 많음 |
| 지시 주입 방식 | system prompt에 카탈로그 설명 덤프 → 작은 모델이 무시하기 쉬움 |
| 지식 계층 단절 | Wiki/코드 인덱스가 있어도 LLM 컨텍스트에 자동 주입되지 않음 |
| 경로 파편화 | 메인챗 / 메일챗 / 캘린더챗 / 로컬 숏컷 — 컨텍스트 공유가 약함 |

---

## 4. 현재 LLM 모델 적합성 평가

### 4.1 현재 기본 모델 (`gemma4:e2b` 계열) 평가

| 항목 | 내용 |
|------|------|
| 한국어 성능 | 소형 Gemma 계열은 일상 대화는 가능하나, 긴 지시·도구 스키마·전문 추론에서 품질 편차 큼 |
| 추론 능력 | e2b급은 Agent multi-step에 불리. 계획→도구→검증 루프가 얕아질 위험 |
| Agent 활용 가능성 | Hermes tool_progress는 지원되나, 소형은 tool call 누락/잘못된 action 이름 위험 (MEMORY nudge가 이를 완화하려 함) |
| Context 처리 능력 | 긴 MCP system + history면 유효 컨텍스트가 빨리 잠식 |
| 속도 | 로컬 소형은 **지연 측면 유리** — 제품 UX와 맞음 |
| 로컬 실행 적합성 | **높음** (기본 설계 목표와 일치) |

**결론:** “빠른 로컬 비서 UX”·설치 게이트에는 적합.  
일상적으로 **클라우드/API를 쓰는 경로**에서는 본 모델이 품질의 주원인이 아니다.  
Agent/코딩/조사 품질은 RAG·Memory·프롬프트·도구 계측을 우선하고, 로컬 소형만 쓸 때에 한해 상위 티어를 검토한다. 모델 변경을 이 문서에서 결정하지 않음.

### 4.2 대체 후보 (검토 필요 여부만)

| 계열 | 검토 필요? | 비고 (결정 아님) |
|------|------------|------------------|
| Qwen 계열 | **예** | 한국어·도구·코딩 균형 후보. TTS도 이미 Qwen 사용 중 |
| Llama 계열 | **예** | fallback에 `llama3.2` 이미 존재. 상위 사이즈 검토 가치 |
| Gemma 계열 | **유지 검토** | 현재 기본. 상위 variant(더 큰 로컬/클라우드)만 옵션 |
| DeepSeek 계열 | **예 (코딩/추론)** | Agent·코드 작업 품질 후보. 로컬 VRAM/라이선스 확인 필요 |
| Mistral 계열 | **선택적** | 도구/속도 균형. 한국어는 벤치 후 판단 |

평가 원칙: **Small Model + MCP** 전략을 유지할지, **중형 로컬**로 올릴지, **클라우드 대형**을 Hermes 뒤에 둘지 3갈래를 먼저 실험 설계.

---

## 5. RAG 적용 필요성 분석

### 5.1 현재 RAG 존재 여부

| 기능 | 존재? | 근거 |
|------|-------|------|
| 문서 벡터 검색 | **없음** | chromadb/faiss/embedding 검색 파이프라인 미검출 |
| Vector DB | **없음** | — |
| Embedding 처리 (지식용) | **없음** | 음성 화자 x-vector만 존재 (`docs/voice.md`) |
| Knowledge Base | **부분** | `IrisWiki` / Obsidian vault / `IrisCodeIndex` — **파일 list/read**, 의미검색 아님 |
| 웹 검색 | **Hermes/SerpAPI 경로로 가능** | `serpapi_client.py`, system prompt에 citation 규칙 |
| 콘텐츠 추출 | **있음** | PDF/URL/Firecrawl (`content_extract.py`) — ingest≠retrieve |

### 5.2 RAG가 필요한 이유 (IRIS 맥락)

IRIS는 “개인형 AI 비서 + IDE Companion + Wiki”를 표방한다 (`SOUL.md`).  
그러나 LLM은 기본적으로 **세션 대화 + 짧은 project_root + MCP 매뉴얼**만 본다.

| 검토 대상 | RAG 필요도 | 이유 |
|-----------|------------|------|
| 프로젝트 문서 | 높음 | 바이브코딩·설명 시 저장소 문서 미주입 |
| 사용자 파일 | 높음 | 드롭/첨부는 턴 단위, 장기 인덱스 없음 |
| 코드 저장소 | 높음 | `code_index`는 목록 수준, 심볼/의미 검색 없음 |
| 대화 기록 | 중간 | `_history` 전부 전송은 스케일 안 됨 → 요약+검색 필요 |
| 사용자 정보 | 중간 | profile/wiki sync는 파일로 존재하나 자동 retrieve 없음 |
| Iris Wiki | 높음 | 노트는 쌓이지만 질문 시 자동 참조 약함 |

**진단:** “지식 저장소는 있고, **지식 회수(RAG)는 없다**.”

---

## 6. MCP 적용 가능성 분석 (구현하지 않음)

### 6.1 이미 있는 것

| 구성요소 | 상태 |
|----------|------|
| `iris/mcp/iris_control_stdio.py` | MCP stdio 서버 — `iris_get_state`, `iris_get_catalog`, `iris_invoke` |
| Hermes sync | `hermes_iris_control_sync` + MEMORY nudge로 도구명 강제 |
| Control surface | UI 액션 카탈로그 (IDE, wiki, email, calendar, learning, voice…) |
| Web | Hermes serpapi provider + Firecrawl 추출 |

즉 **UI Control MCP는 이미 Level 3 일부**다. 부족한 것은 Memory/File/Code/Web을 **표준 MCP 역할로 분리·강화**하는 설계.

### 6.2 Memory MCP

| 항목 | 분석 |
|------|------|
| 필요한 이유 | `_history`/SOUL만으로는 사용자 장기 선호·결정·프로젝트 관례가 유지되지 않음. MEMORY.md nudge는 도구 사용법 고정용 |
| 적용 위치 후보 | Hermes memory slot 앞단, 또는 `_chat_messages_with_project_context` 직전 retrieve 훅 |
| 기대 효과 | 반복 설명 감소, 개인화, 세션 간 일관성 |

### 6.3 File MCP

| 항목 | 분석 |
|------|------|
| 필요한 이유 | Wiki/첨부/프로젝트 파일을 모델이 필요할 때만 읽게 해야 함. 현재는 전부 넣거나 안 넣음 |
| 적용 위치 후보 | `iris_invoke`의 wiki/project 액션 확장 또는 독립 File MCP → Hermes tools |
| 기대 효과 | 컨텍스트 절약 + 정확한 근거 인용 |

### 6.4 Web Search MCP

| 항목 | 분석 |
|------|------|
| 필요한 이유 | 최신 정보·사실 검증. SerpAPI는 있으나 Hermes 스킬 의존, Iris 네이티브 MCP로 일관되지 않음 |
| 적용 위치 후보 | Hermes web tool 유지 또는 Iris MCP로 래핑해 citation 강제 |
| 기대 효과 | 환각 감소, Sources 칩 UX와 정합 (`main_window` citation 규칙) |

### 6.5 Code MCP

| 항목 | 분석 |
|------|------|
| 필요한 이유 | `project.run`/`write_file`은 있으나, 정적 분석·테스트·오류 루프는 Agent 자율성에 의존 |
| 적용 위치 후보 | IDE companion + `project.run` 결과 피드백을 도구로 표준화 |
| 기대 효과 | 바이브코딩 성공률, 오류 자기복구 |

---

## 7. Agent Architecture 분석

### 7.1 레벨 정의 대비 현황

| Level | 형태 | IRIS 해당 여부 |
|-------|------|----------------|
| 1 | User → LLM → Answer | **Hermes OFF + Ollama/API 직행** 시 해당 |
| 2 | User → Intent → LLM → Answer | **부분 해당** — 로컬 IDE/wiki/workspace 숏컷, `voice_intents` (전화/알림) |
| 3 | User → Planner → Tool Router → MCP → LLM → Answer | **Hermes ON 시 근접** — Planner/Router는 Hermes 쪽, Iris는 MCP 도구 제공 |

### 7.2 판정

**현재 IRIS = Level 2 + (조건부) Level 3 하이브리드**

```
[항상] 규칙 인텐트 / 로컬 숏컷 ──┐
                                 ├─→ (필요 시) LLM
[Hermes ON] Hermes Agent + MCP ──┘
[Hermes OFF] 순수 LLM ──────────────→ Answer
```

- Iris 앱 내부에 독자적 multi-agent / explicit Planner 모듈은 **없음** (`assistant/external_agent_adapter.py`는 상태 표시용).
- Agent 능력의 중심은 **외장 Hermes**에 위임.
- 따라서 “Agent 구조 부족”은 Iris 코어 기준으론 맞고, Hermes 포함 시스템 기준으론 부분적으로 이미 존재한다.

---

## 8. 개선 방향 우선순위 제안 (구현 순서만)

문서 상단 **「총괄. 개선 예정 사항 요약표」**가 정식 대장이다. 아래는 동일 내용의 순위만 요약한 것이다.

| 순위 | 총괄 연번 | 개선 항목 | 예상 효과 | 난이도 |
|------|-----------|-----------|-----------|--------|
| 1 | 4 | Hermes·도구 **성공률 계측** + Offline SLA | 품질 관측·회귀 탐지 | 낮음 |
| 2 | 2 | **Memory** (세션 요약 + 장기 retrieve) | 반복·기억상실 감소 | 중 |
| 3 | 1 | Wiki/코드/문서 **경량 RAG** | 근거 있는 답변, 환각↓ | 중~높 |
| 4 | 3·6 | MCP 역할 분리 + Iris **Intent Router** | 지시 과다↓, 불필요 LLM 호출↓ | 중 |
| 5 | 5 | **모델 티어 정책** (소형/클라우드 — 벤치 후) | 품질·속도 트레이드오프 | 중 |
| 6 | 7 | 메일·캘린더·메인챗 **맥락 정합** | 워크스페이스 단절 완화 | 중 |
| 7 | 8 | Multi Agent (조사/코딩/일정) | 복합 작업 안정화 | 높 |
| 8 | 9 | Large Model / Kimi 등 **연구** | 장기 차별화 | 높 (연구) |

> Hermes 경로 **고정은 완료**(총괄 항 A). 모델 교체만으로 해결하려 하지 말 것. 병목은 **회수(RAG/Memory) + 지시·도구 관측**이다.

---

## 9. 최종 진단 요약

### 현재 IRIS 상태

**로컬 음성·IDE Companion·Hermes(필수) MCP를 갖춘 Level 2~3 하이브리드 데스크톱 비서.**  
기획은 「클라우드·로컬 모델 + Hermes」이며 Hermes 고정은 **완료**.  
지식은 “저장”되나 “회수(RAG)”되지 않고, system에 MCP 매뉴얼을 과적재하는 구조다.  
설치 최소 모델(`gemma4:e2b`)은 게이트용이며, 일상 품질 주원인으로 단정하지 아니한다.

### 가장 큰 문제점 TOP 5 (재확인 후)

1. **문서/코드/위키 RAG 부재** → 지식 기반 답변 불가  
2. **장기 Memory 부재** (세션 `_history` + MEMORY nudge 수준)  
3. **System prompt에 MCP 매뉴얼 과다 주입** → 지시 준수율·토큰 효율 저하  
4. **Hermes·도구 품질 미계측** / gateway Offline 시 체감 급락  
5. **소형 로컬 선택 시에만** 모델↔Agent 난이도 불일치 (조건부)

### 가장 효과적인 개선 방향 TOP 5

1. Hermes·도구 **계측** (성공률·citation·재질문·Offline)  
2. Wiki/프로젝트 **최소 RAG**  
3. 대화/프로필 **Memory retrieve**  
4. MCP 역할 분리 + Iris **Intent Router**  
5. 모델 티어 정책 — **벤치 후**, 클라우드 기본 경로와 분리 기술

### 다음 개발 단계 추천

1. **계측 먼저** (총괄 연번 4)  
2. **Memory MVP** (연번 2)  
3. **Wiki RAG MVP** (연번 1)  
4. 그 다음 MCP 분리·Router·모델 티어 실험

### 장기 연구 방향

| 방향 | 의미 |
|------|------|
| Small Model + MCP | 현재 DNA. 소형은 라우팅·도구 호출에 집중, 지식은 MCP/RAG로 |
| RAG | Wiki·코드·사용자 파일의 기본 지능 인프라 |
| Multi Agent | 조사 / 코딩 / 일정·메일 에이전트 분리 |
| Local Large Model | VRAM 허용 시 단일 고품질 로컬 경로 |
| Kimi K3 Runtime 연구 | 초장문·에이전트 런타임 후보로 PoC 수준 연구 (제품 기본값 결정 전제 아님) |

---

## 부록 A. code-review-graph 관찰 요약

| Community | Size | AI 관련성 |
|-----------|------|-----------|
| `window-event` | 1713 | UI 오케스트레이션 (채팅 진입점) |
| `audio-voice` | 248 | STT/TTS/VAD 전체 |
| `infrastructure-model` | 184 | Ollama/Hermes/API 클라이언트 |
| `knowledge-wiki` | 64 | 비벡터 지식 계층 |
| `runtime-intent` | 26 | UserTurn + 규칙 인텐트 |
| `mcp-tool` | 10 | Iris Control MCP |
| `serpapi-search` | 13 | 웹 검색 클라이언트 |

Critical flow: `_dispatch_user_turn` (depth 9, 229 nodes) — 채팅·Hermes/Ollama·TTS·IDE까지 한 줄기에 묶여 있음 → **AI 코어가 MainWindow에 집중**.

## 부록 B. 검증용 핵심 파일 인덱스

| 주제 | 파일 |
|------|------|
| Entry | `iris/__main__.py` |
| Turn 오케스트레이션 | `iris/ui/window/main_window.py` |
| Hermes 스트림 | `iris/infrastructure/hermes_client.py`, `iris/ui/workers/hermes_workers.py` |
| Ollama 스트림 | `iris/infrastructure/ollama_client.py`, `iris/ui/workers/ollama_workers.py` |
| 기본 모델 | `iris/system/setup_protocol.py` |
| SOUL | `integrations/hermes-soul/SOUL.md` |
| MCP | `iris/mcp/iris_control_stdio.py` |
| STT | `services/voice_runtime/stt_service.py` |
| TTS | `services/voice_runtime/tts_stream.py` |
| Memory nudge | `iris/system/hermes_memory_nudge.py` |
| Wiki | `iris/knowledge/iris_wiki.py` |

---

*본 문서는 진단 전용이다. 상단 총괄표 우선순위에 따른 구현은 별도 작업 요청 시에만 진행한다.  
2026-09-23: 기획(Hermes 필수·클라우드+Hermes) 및 코드 재대조 반영.*
