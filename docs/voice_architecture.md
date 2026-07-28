# Voice Architecture

## 구성

- `iris/audio/`
  - UI 쪽 클라이언트, 녹음, 워커, 텍스트 정리
- `services/voice_runtime/`
  - localhost 전용 FastAPI 런타임 (`127.0.0.1:18765`)
- `iris/storage/voice_prefs.py`
  - SQLite `user_preferences` 키 `voice_prefs_v1`
- `scripts/`
  - `.venv-voice` 설치, manifest/export 유틸

## 런타임 경계

- GUI 스레드: 버튼/상태/재생 제어만
- 별도 프로세스 (`.venv-voice`): STT/TTS 모델 로딩 및 추론
- 워커 스레드 (`QThread`): HTTP 호출과 UI 비동기 연결
- 앱 종료: `VoiceRuntimeProcessManager.shutdown()` → `POST /shutdown`

## API

- `GET /health`
- `POST /v1/audio/transcriptions`
- `POST /v1/audio/speech`
- `POST /v1/voice/prepare`
- `POST /v1/voice/analyze`
- `GET /v1/voice/references`
- `POST /v1/voice/reference`
- `POST /v1/voice/cache/clear`
- `POST /shutdown`

## STT 흐름

1. 마이크 버튼 → `AudioRecorder` 시작 (레벨 → waveform)
2. 다시 클릭 → wav 생성 → `STTTranscriptionWorker`
3. runtime `/v1/audio/transcriptions`
4. 결과를 `ChatPanel.insert_input_text`로 append (덮어쓰기/자동전송 없음)
5. GPU면 float16, 실패/비가용이면 CPU int8

## TTS 흐름

1. 최종 답변 완료 + `tts_mode=auto` 또는 답변별 🔊
2. `normalize_tts_text` + `split_tts_sentences`
3. reference 존재 확인 → `/v1/voice/prepare` (hash 캐시)
4. 세그먼트별 `/v1/audio/speech` → `QSoundEffect` 순차 재생
5. 새 재생 시작 시 기존 큐/재생 정리

## 녹음 폴더 분석

- 재귀 검색: `.wav .mp3 .m4a .flac .ogg .aac`
- 원본 수정 금지
- quality_score + (가능 시) 참고용 전사
- 추천은 단일 파일 top 5 (합치기 없음)

## mock / 실제

- 환경변수 `VOICE_RUNTIME_MOCK` (기본 1)
- 설정창 mock 체크박스가 프로세스 기동 시 반영
- 실제 모드에서 모델 미설치면 명확한 오류 (가짜 성공 없음)

## 현재 구현 메모

- 기본은 mock-friendly → CI에서 대형 모델 다운로드 금지
- `setup_voice_runtime.ps1 -Full` 로 torch/qwen-tts 추가 설치
