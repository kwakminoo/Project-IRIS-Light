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

### qwen-tts 호출 규약 (실측으로 확정, 바꾸지 말 것)

- `language="korean"` — **소문자**. 문자열이 프로세서 프롬프트에 그대로 들어가므로
  `"Korean"`으로 주면 발음이 깨진다.
- `x_vector_only_mode=True` — 화자 임베딩만 사용. ICL 모드는 `ref_text`가 기준 음성과
  정확히 일치해야 해서 불안정하다.
- 모델 로딩은 **bf16** (`dtype=torch.bfloat16`). fp16은 CUDA device-side assert로 죽는다.
- 클로닝은 `*-Base` 모델 전용 (`tts_model_type == "base"`).
- `generate_voice_clone`은 파일 경로가 아니라 `(파형 리스트, sample_rate)`를 반환한다.
  런타임이 직접 16bit PCM wav로 저장한다.
- 위 규약은 `tests/test_tts_service_contract.py`가 고정한다. mock 모드는 실제 모델을
  호출하지 않으므로 시그니처 오류를 잡아주지 못한다.

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
