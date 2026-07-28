# Voice

Iris Light의 음성 기능은 메인 `.venv`와 분리된 `.venv-voice` 런타임을 사용합니다.
FastAPI 런타임은 **`127.0.0.1:18765`에만** 바인딩됩니다.

## 현재 실제로 되는 것

- 설정창 음성 섹션 저장/로드 (SQLite `voice_prefs_v1`)
- 마이크 녹음 → STT → 채팅 입력창에 append (자동 전송 없음)
- 답변별 🔊 수동 TTS, `tts_mode=auto` 시 최종 답변 후 자동 TTS
- 문장 분할 순차 재생 / 중지 / 캐시 정리
- 녹음 폴더 분석 → `~/.iris-light/voice/manifest.jsonl` + `manifest.csv`
- 추천 참고 음성 top 5 표시, 기준 음성/대본 확정
- **mock 모드**에서 STT/TTS HTTP 경로 검증 (모델 다운로드 없이)

## 아직 제한된 것

- 실제 faster-whisper / Qwen3-TTS 품질은 `.venv-voice`에 모델 설치 + mock 해제 후 별도 검증 필요
- m4a 등 비-WAV는 `soundfile`(+시스템 디코더)이 있어야 길이/RMS 분석 가능
- QTextEdit 기반 채팅이라 스피커 상태는 아이콘(🔊/⏳/▶/⚠) 수준
- 여러 파일을 하나의 reference로 합치지 않음 (단일 파일만)

## 설치

```powershell
# mock/스모크용 (권장 기본)
.\scripts\setup_voice_runtime.ps1

# 실제 TTS 모델까지
.\scripts\setup_voice_runtime.ps1 -Full
```

또는

```bat
.\scripts\setup_voice_runtime.bat
.\scripts\setup_voice_runtime.bat -Full
```

## 녹음 폴더 분석

기본 폴더(존재 시 프로젝트 내 동명 폴더로 폴백):

`c:\Users\kwakm\Desktop\1차 아이리스 녹음`

```powershell
# 메타만 (전사 생략)
$env:VOICE_RUNTIME_MOCK=1
.\.venv-voice\Scripts\python.exe scripts\prepare_voice_dataset.py "경로" --no-transcript

# 설정창: 녹음 폴더 선택 → "녹음 폴더 분석"
```

결과:

- `~/.iris-light/voice/manifest.jsonl`
- `~/.iris-light/voice/manifest.csv`

## 기준 음성 선택

1. 추천 목록에서 미리듣기/선택
2. 참고 대본을 사용자가 수정
3. **기준 음성 확정** → `voice_clone_prompt` hash 캐시
4. 테스트 문장으로 생성/재생 확인

## mock vs 실제

| | mock (`VOICE_RUNTIME_MOCK=1`) | 실제 (`0`) |
|--|--|--|
| STT | `[mock stt] …` 고정 문구 | faster-whisper |
| TTS | 무음 wav 생성 | Qwen3-TTS voice clone |
| 용도 | UI/연동/테스트 | 실제 음성 |

모델 미설치여도 메인 앱(채팅/Wiki/이메일)은 계속 사용 가능합니다.

## 데이터 경로

- 생성 음성: `~/.iris-light/audio/generated/`
- manifest/선택: `~/.iris-light/voice/`
- 모델 캐시: `~/.iris-light/models/`

## 개인정보 / 동의

- 음성 데이터는 로컬에서만 처리됩니다.
- 성우 본인의 동의와 사용 권한이 필요합니다.
- 제3자 목소리 무단 복제는 금지입니다.
