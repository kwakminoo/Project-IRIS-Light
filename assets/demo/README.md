# Demo GIF 스펙

README의 `## Demo` 섹션에 들어가는 GIF 4개를 이 폴더에 넣습니다.
파일을 추가한 뒤 각 언어별 README에서 해당 이미지 줄의 `<!-- -->` 주석만 풀면 됩니다.

## 공통 규칙

| 항목 | 값 |
|------|------|
| 형식 | GIF (또는 `.mp4` → GIF 변환) |
| 폭 | 960px 권장 (README 렌더링 폭 기준) |
| 길이 | 항목당 8~15초 |
| 용량 | **파일당 5MB 이하** (GitHub README 로딩 속도) |
| 프레임 | 12~15fps (텍스트 가독성 우선) |
| 개인정보 | 메일 주소·API 키·실명 노출 금지 (설정에서 더미 계정 사용) |

## 파일 목록

| 파일 | 담을 내용 | 촬영 포인트 |
|------|------|------|
| `main.gif` | HUD 전체 첫인상 (선택) | 앱 실행 → HUD 등장 → 탭 이동 |
| `agent.gif` | Agent Execution | 자연어 입력 → 사고/도구 로그 스트리밍 → 파일 생성 결과 |
| `voice.gif` | Voice Interaction | 마이크 입력 → STT 인식 텍스트 → 응답 → TTS 재생 표시 |
| `runtime.gif` | Runtime Architecture | 시작 위저드 또는 모니터에서 Ollama·Hermes gateway 기동 상태 |
| `setup.gif` | Installation | `IRIS-Setup.exe` 실행 → 자동 설치 진행 → 바탕화면 아이콘 |

## 녹화 참고

- 촬영 대본과 나레이션은 [`docs/demo-video-script.md`](../../docs/demo-video-script.md)에 있습니다.
- 실제 설치 없이 UI만 보여 주려면 `IRIS_SETUP_DEMO=1` / `IRIS_SETUP_DRY_RUN=1` 환경변수를 사용합니다.
