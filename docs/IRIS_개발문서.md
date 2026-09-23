# IRIS 개발 문서

| 항목 | 내용 |
|------|------|
| 문서명 | IRIS Light 개발 기준서 |
| 대상 | Project-IRIS-Light |
| 표시명 | IRIS |
| 성격 | 공문서 · 표기 요약 |
| 갱신 | 2026-09-22 |

---

## 1. 제품 정의

| 구분 | 내용 |
|------|------|
| 한 줄 | Ollama(모델) + Hermes(도구·MCP)를 감싸는 PyQt6 데스크톱 HUD |
| IRIS 역할 | UI · 세션 · Control Surface · Setup · 워크스페이스 |
| IRIS 비역할 | 자체 NL 오케스트레이터 · 웹검색/셸/파일IO 재구현 |
| 실행 | `dist/IRIS.exe` → `.venv\Scripts\pythonw.exe -m iris` |

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| UI | PyQt6 |
| 언어 | Python 3 |
| 로컬 모델 | Ollama `:11434` |
| Agent | Hermes Gateway `:8642` |
| 역제어 | Control Surface `:8765` + MCP `iris_control` |
| 음성(옵션) | Voice Runtime `:18765` (`.venv-voice`) |
| 저장 | SQLite (`~/.iris-light`) |
| 패키징 | thin launcher exe (풀번들 금지) |

---

## 3. 디렉터리

| 경로 | 역할 |
|------|------|
| `iris/ui/` | Frontend · MainWindow · Chat · Workspace |
| `iris/runtime/` | UserTurn · 음성 규칙 인텐트 |
| `iris/infrastructure/` | Ollama · Hermes · OpenAI-compat · SerpAPI |
| `iris/system/` | Setup · IDE · Hermes/Ollama 기동 · Control |
| `iris/mcp/` | Iris Control MCP stdio |
| `iris/audio/` | 마이크 · VAD · STT/TTS 클라이언트 |
| `iris/knowledge/` | Wiki · 코드 인덱스 · 추출 |
| `iris/storage/` | DB · 프로필 · 설정 |
| `iris/learning/` | Aloha 화면학습 |
| `services/voice_runtime/` | STT/TTS 서비스 |
| `integrations/hermes-soul/` | SOUL.md 페르소나 |
| `scripts/` | 빌드 · voice setup |
| `tests/` | 계약·단위 테스트 |
| `docs/` | 개발·IA·음성·코드리뷰 |

---

## 4. 런타임 포트

| 구성요소 | 포트/경로 | 비고 |
|----------|-----------|------|
| Ollama | `11434` | `/api/chat` · 로컬/클라우드 |
| Hermes | `8642/v1` | `/chat/completions` · tools |
| Control Surface | `8765` | Hermes → Iris UI 역제어 |
| Voice Runtime | `18765` | faster-whisper · Qwen3-TTS |
| 기본 모델(설치) | `gemma4:e2b` | Setup 기본값 |

---

## 5. 요청 처리 흐름

| 단계 | 처리 |
|------|------|
| 1 | 입력 (키보드 / 음성 / 첨부) |
| 2 | `UserTurnDispatcher` → `MainWindow._execute_user_turn` |
| 3 | 로컬 숏컷 (IDE · Wiki · Workspace · 전화 인텐트) |
| 4 | STT (음성) → faster-whisper `small` |
| 5 | LLM → Hermes(권장) / Ollama 직행 / API 직행 |
| 6 | 스트림 UI · tool_progress |
| 7 | TTS (옵션) → Qwen3-TTS |

| Hermes | 동작 |
|--------|------|
| ON | 선택 모델 전부 Hermes Agent (MCP 유지) |
| OFF | Ollama 또는 OpenAI-compat 직행 (도구 없음) |

---

## 6. MCP · 도구

| 도구 | 용도 |
|------|------|
| `iris_get_state` | UI/세션 상태 |
| `iris_get_catalog` | 액션 목록 |
| `iris_invoke` | IDE · Wiki · Email · Calendar · Voice · Learning 등 |

| 금지 | 이유 |
|------|------|
| 터미널로 IDE 단독 실행 | Companion 타일 우회 |
| Hermes 내장 terminal | 비활성 · `project.run` 사용 |

---

## 7. AI 파이프라인 요약

| 구분 | 모델/방식 |
|------|-----------|
| STT | faster-whisper · default `small` · `ko` |
| LLM | Ollama + Hermes · 페르소나 `SOUL.md` |
| TTS | `Qwen/Qwen3-TTS-12Hz-0.6B-Base` |
| Prompt | Hermes: SOUL identity · Ollama 직행: SOUL 주입 |
| Context | in-memory `_history` + project_root + MCP 지침 |
| RAG | 미구현 (Wiki는 파일 저장만) |

---

## 8. UI · IDE 계약

| 항목 | 규칙 |
|------|------|
| IDE Companion 비율 | 정수 픽셀 8:2 (`ide_w + iris_w == work_w`) |
| IRIS IDE 배치 | `place_qt_window` / `setGeometry` only |
| Cursor 배치 | `place_hwnd` |
| seam overlap | 금지 |
| new_window | 기본 `True` · 빈 창 후 folder inject |
| exe | thin launcher 유지 · frozen 풀번들 금지 |

---

## 9. Agent 레벨

| Level | 형태 | IRIS |
|-------|------|------|
| 1 | User → LLM → Answer | Hermes OFF |
| 2 | Intent → LLM | 로컬 숏컷 · voice_intents |
| 3 | Planner → Tools → MCP | Hermes ON (근접) |

**판정:** Level 2 + 조건부 Level 3 하이브리드

---

## 10. 개발 금지 · 의무

| 구분 | 내용 |
|------|------|
| 금지 | `IRIS_launcher` frozen 번들 회귀 · seam overlap · Companion에 IDE Win32 sync 오용 |
| 금지 | 아이콘 검정 불투명 배경 |
| 의무 | IRIS 관련 수정 후 `dist\IRIS.exe` / 바로가기 대상 확인 |
| 의무 | 빌드 필요 시 `scripts\build_iris_exe.ps1` |
| 커밋 작성자 | `kwakminoo` / `kwakmw12@naver.com` |

---

## 11. 관련 문서

| 문서 | 경로 |
|------|------|
| 도메인 | `docs/domain.md` |
| IA | `docs/ia/IA.md` |
| 음성 | `docs/voice.md` · `docs/voice_architecture.md` |
| API | `docs/api/API-명세서.md` |
| AI 진단 | `docs/코드리뷰/IRIS_AI_Architecture_Diagnosis.md` |
| 코드리뷰 조치 | `docs/code-review/조치-소요-사항-총괄표.md` |

---

## 12. 개선 우선순위 (참고)

| 순위 | 항목 |
|------|------|
| 1 | Hermes+MCP 경로 품질 고정 · 계측 |
| 2 | Memory (세션 요약 · 장기 기억) |
| 3 | Wiki/코드 경량 RAG |
| 4 | MCP 역할 분리 (Memory/File/Web/Code) |
| 5 | Intent Router · 모델 티어 |
| 6 | Multi Agent · Local Large Model 연구 |
