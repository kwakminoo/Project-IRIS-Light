# IRIS Agent Core 최종 검증 및 Wave 1 릴리스 판정

2026-11-25 · ACF-00–15 · 기준 HEAD `1ab0452aff9c25c9e9871d1917e3d8dde6ae03b8`

## 판정

**NO-GO · 기존 사용자 엔진 전환 및 Wave 1 릴리스**

Windows의 분리된 Agent Home에서 `iris-agent-core 0.1.1+iris.a382af23`의 설치, 선택 모델 호환성 검사, 업데이트 및 롤백을 실행했다. 신규 환경에는 별도 `hermes-agent` checkout이 없었다. 기존 사용자는 전체 제품 동등성 게이트가 통과할 때까지 현재 엔진을 사용한다. 배포 번들의 `legacy_migration_approved`는 `false`다. 기존 사용자 홈을 전환한 증거로 테스트 홈의 결과를 사용하지 않았다.

| 게이트 | 판정 | 근거 |
|---|---|---|
| Wave 1 전체 | NO-GO | Reference와 Owned의 GUI 사용자 시나리오 전수 비교가 남음 |
| IRIS Engine Independence | CONDITIONAL | Windows 테스트 홈에서 설치, 모델 호출, 갱신, 롤백 증명. 실제 사용자 전환과 운영체제별 검증은 남음 |
| Native Tool Independence | CONDITIONAL | Home/IDE 각각 115개 Schema 매핑, 원본 Dispatcher 차단 및 Owned GUI의 실제 `terminal` → `shell.run` Host 라우팅 확인 |
| Product Stability | NO-GO | FPR 자동 회귀와 실제 Owned GUI 착지 확인. 재시험에서 모델 도구 결과가 실패하고 답변이 요청을 완료하지 못함 |
| Security | CONDITIONAL | 원본 Dispatcher 및 inline 우회 차단, 기존 승인 계약 자검. 실제 외부 승인 표면 전수는 미완 |
| Wave 2 착수 | NO-GO | Wave 1 승인 이후 재판정. Wave 2와 Wave 3 계획 유지 |

## 이전 단계와 기준선

| 단계 | 인수한 결과 |
|---|---|
| Wave 1 / 1.1 | IRIS 관리 실행 경계와 보안 계획을 후속 단계의 기준으로 유지 |
| Wave 1.2 | 기존 리포트의 Agent Turn, Shell, IDE, 작업공간 및 보안 점검 결과를 인수 |
| Wave 1.2 Hotfix | 승인과 작업공간 수리의 자동 검증을 인수. 실제 IDE와 장시간 작업 전수는 FPR에 이월 |
| Wave 1.3 Native Tool Unification | 이전 증거의 `gpt-oss:20b` GUI terminal 턴에서 `shell.run owner=iris` 확인. Home/IDE 115개 Schema 매핑을 재실행 |
| Final Product Repair / Unified Approval | 이전 최종 게이트는 CONDITIONAL. Shell Box 표시, Control process 호출, 카드 승인 및 DB 착지 자검 증거가 있었으며 사용자 13개와 추가 GUI 전수는 미완 |
| Core Ownership | 재사용한 벤더 소스와 MIT 출처 확립. 이전 Owned 확인은 주로 복사·계약 확인이었으며 설치된 Reference의 모델 턴과 구분 |
| Core Finalization | 실제 `.venv` 설치, Owned Core import, 안전한 선택/복구, 앱 설치 진입 경로, 실제 모델 호출 검증을 추가 |

기존 Wave 1.3 및 FPR 파일은 작업 시작 시 작업 트리에 있던 변경이었다. 이전 검증 결과와 이번에 재실행한 결과를 별도로 기록했다. [Wave 1.2](completed/iris-agent-wave12-final-report.md) · [Hotfix](completed/iris-wave12-hotfix-validation-report.md) · [Wave 1.3](completed/iris-agent-wave13-native-tool-unification.md) · [FPR 게이트](fpr-14-final-product-repair-gate.md) · [Ownership](completed/iris-agent-core-ownership-final-report.md)

## ACF-00 엔진 인벤토리

| 항목 | Reference / 기존 사용자 | Owned 검증 환경 |
|---|---|---|
| 소스 | `%USERPROFILE%\.iris-light\agent\hermes-agent` | `vendor/iris-agent-core`, `vendor/iris-agent-runtime/PIN` |
| 설치 디렉터리 | `%USERPROFILE%\.iris-light\agent\hermes-agent` | 워크스페이스 `.tmp/acf-product/iris-agent.slot-0b0c55760140435c` |
| 인터프리터 | 설치 디렉터리 아래 `venv/Scripts/python.exe`, CPython 3.14.7 | Owned 슬롯 아래 `venv/Scripts/python.exe`, CPython 3.14.7 |
| Agent 클래스 | Reference checkout의 `run_agent.AIAgent` | Owned 슬롯의 `run_agent.AIAgent`, 제품 진입 `iris.engine.agent_entry` |
| 배포 메타데이터 | `hermes-agent 0.0.0` | `iris-agent-core 0.1.1+iris.a382af23` |
| 버전 근거 | Reference checkout에서 Git HEAD `a382af23f4c067d23463b5781958684c2cda82bc` 직접 확인 | `SOURCE_MANIFEST.json`, `pyproject.toml`, `uv.lock`, 선택 파일 `iris-engine-selection.json` |
| 모델 / Provider | `gpt-oss:20b`, Ollama OpenAI-compatible `custom` 대상으로 실제 요청 | 같은 대상. 별도 Cloud API 및 Provider 전수는 미검증 |
| 데이터 | Agent Home의 config, dotenv, 자격 증명, state/session DB, 메모리, 스킬, SOUL. UI DB와 Shell 승인 파일은 `.iris-light` | 설치 및 업데이트는 슬롯과 선택 파일을 사용. 사용자 데이터 경로를 엔진 슬롯과 분리 |
| 환경 | `IRIS_AGENT_HOME`이 제품 홈을 선택. 코어 호환 `HERMES_HOME`은 sidecar 시작 시 엔진이 지정 | Probe는 상속된 Python 경로를 제거하고 `-I`를 사용. UV 환경을 후보 슬롯으로 지정 |
| 업데이트 | 이전 구현은 live checkout에 파일을 덮어쓰고 소스가 없으면 Git fetch를 시도할 수 있었음 | 애플리케이션 번들의 Manifest 비교와 잠금 의존성 설치 후 준비·모델 검사 및 선택 파일 전환 |

설치된 양쪽 환경에서 `openai 2.54.0`, `httpx 0.28.1`, `requests 2.34.2`, `ruamel.yaml 0.18.16`을 확인했다. Reference의 `mcp 2.0.0`과 `python-dotenv 1.2.2`는 Owned에서 각각 `2.3.0`, `1.2.4`였다. Reference의 `aiohttp 3.14.3`은 Owned 제품 프로필의 필수 패키지가 아니며 설치 단계에서 검증 대상을 실제 AIAgent로 바꿨다.

## 제품 실행 경로

```text
IRIS Desktop / SQLite
  → InternalSidecar / 선택된 Python 및 AIAgent
  → IRIS Native Registry의 표면별 Schema
  → IRIS Host Dispatcher / canonical action / trusted context
  → 채팅 승인 및 실행 정책 / Execution Runtime
  → IRIS Product Tool / 결과 및 GUI 표시
```

Host는 도구 이름·Schema fingerprint·turn·session·workspace를 검증한다. 선택된 IRIS 바인딩은 sidecar에서 `model_tools.handle_function_call`을 직접 연결하고, 원본 registry 직접 dispatch는 차단한다. Owned Core는 동시·순차 실행에서 원본 inline, memory-provider 및 delegate handler를 건너뛴다. CLI 방향의 원본 소스와 MIT 라이선스는 벤더에 보존했다.

실제 GUI 첫 시도에서 sidecar stdout만 사용한 tool request가 Host에 전달되지 않았다. 도구 요청을 원자적으로 발행한 파일로 넘기고 동일 request ID를 한 턴에서 한 번만 처리하도록 바꿨다. 다시 실행한 GUI에서 Host가 요청을 받아 `shell.run owner=iris`로 전달했고 최종 SQLite 착지까지 완료했다.

## 구현 및 잔여 작업

| ACF | 상태 | 구현 및 검증 범위 |
|---|---|---|
| 00 | 완료 | 실제 작업 트리, 이전 게이트, 엔진·통합·사용자 홈 및 실행 경로 조사 |
| 01 | 구현 / Windows 증명 | Desktop 환경 `win32`, `darwin`, `linux`, Python 3.14. `uv.lock` Git 허용, 루트 배포 이름 및 self-extra 정정, build 도구 버전 고정. Manifest는 핵심 시작 소스와 메타데이터, 출처 및 lock을 SHA-256으로 확인 |
| 02 | Windows 통과 | 신규 cache의 검증 설치가 Git 접근 금지 상태로 88개 라이브러리를 설치. 수정 최종 패키지는 별도 슬롯에서 잠금 cache를 사용해 다시 설치 및 모델 검증 |
| 03 | Windows 통과 | 슬롯 이름과 절대 Venv 경로 유지, 프로세스 간 설치 잠금, 원자적 선택, 이전 슬롯 복구. 소스 복사, lock/install, import/ready/model, 선택 실패와 중단 후 기존 선택 보존 검사 |
| 04 | 기본 경로 구현 | Wizard 설치·복구는 같은 Owned 계약. Setup 검증에는 실제 모델 턴을 사용. 앱 업데이트에서 upstream fetch와 live source 덮어쓰기를 제거. 새 홈에 외부 엔진 Fallback 없음 |
| 05 | 실행 권한 차단 | 원본 registry 및 inline dispatch 차단. 원본 registry/handlers 제거는 동적 참조와 전체 동등성 검증 이후 |
| 06 | 부분 | 제품 채팅 및 설치 검증은 InternalSidecar. 기존 Gateway 진단, provider config 유틸리티와 명시적 호환 경로의 물리적 분리는 보류 |
| 07 | 부분 | 잠금 설치에서 bake된 overlay 재적용 제거. Owned 패키지는 `iris-agent`, `iris` CLI만 생성. 이름 호환 모듈 및 향후 Headless 구현 소스 보존 |
| 08 | 부분 | 기본 자동 동기화에서 MCP 실행 점검 제외. 설정에서 명시적으로 점검 가능. 기존 SOUL 보존, 새 홈은 IRIS 기본 SOUL 시드. Mobile 및 일반 MCP 설정 보존 |
| 09 | 소스 확인 | 아래 자산 표 참조. 비활성 도구를 제품 등록하지 않음 |
| 10 | 보류 | 기존 환경은 동등성 게이트 뒤 전환. 기존 폴더, 사용자 설정, 인증정보와 데이터베이스는 이동하지 않음. 격리된 성공·실패 복구 분기 확인 |
| 11 | 부분 | 실제 Reference와 Owned의 동일한 로컬 모델 일반 응답. 전체 13개 및 FPR GUI 비교 미완 |
| 12 | 분리 실행 통과 / 배포 보류 | 별도 Hermes checkout 없는 테스트 홈에서 실제 Owned 실행. 기존 사용자 기본 엔진 전환 보류 |
| 13 | 보류 | 기존 소스와 감사 아티팩트 보존. 물리 삭제 조건인 전체 회귀 증거가 남음 |
| 14 | 부분 | 아래 증거와 미검증 항목 참조 |
| 15 | 완료 | 최종 상태와 잔여 게이트를 이 문서에 기록 |

### 남은 자산

| 분류 | 자산 |
|---|---|
| IRIS Core 흡수 | Conversation Loop, Provider Adapter, Tool Call Parsing, Context Compression, 오류 복구 기술. 각 경로의 모든 실행 분기는 미검증 |
| IRIS로 대체 | 제품 Tool Registry, Dispatcher, Trusted Context, 승인, Shell/Process, patch/file, Wiki/Browser/Web과 GUI 중심 Session DB |
| 독립 실행 권한 제거 | 제품 sidecar의 원본 Registry/inline dispatch, 설치 시 외부 Git fetch 및 upstream installer 호출. 벤더 소스는 보존 |
| 격리 / Reference | `vendor/iris-agent-runtime` provenance/overlay 기준, 기존 Reference checkout, Gateway 호환 모듈·CLI shim, `scripts/iris_hermes_bench`, `scripts/apply_env_to_hermes.ps1` |
| 유지 및 이후 정리 | `integrations/hermes-mcp` 호환 자산, `integrations/hermes-skills`의 사용 중 IRIS 스킬, `integrations/hermes-plugins`의 SerpAPI 소스, `integrations/hermes-soul`의 기본 Identity. 일반 MCP, Mobile/Emulator 및 사용자의 API 설정 유지 |
| Wave 2 | Memory/Skills Manager, Task Planning, Clarification, Subagent, Vision, Computer Use의 제품 흡수. 미흡수 15개 도구를 향후 IRIS Registry에서 직접 등록하도록 소스 보존 |
| Wave 3 | Headless/Batch, Trajectory Recorder/Compressor, 관측 경계 소스 보존. 학습 파이프라인 전수 검증은 Wave 3 범위 |
| 라이선스·외부 의존 | Nous MIT `LICENSE`, `PROVENANCE.md`, `THIRD_PARTY_NOTICES.md`. 새 설치는 Python 3.14, UV, 잠금된 일반 Python 배포물 및 추론 Provider 필요. 비활성 옵션의 별도 pin 및 라이선스도 유지 |

`uv sync --locked` 설치는 미리 다운로드한 캐시에서 동작했다. 완전한 신규 오프라인 설치에는 호환 Python, UV, build 및 runtime 패키지 캐시가 필요하다. `uv lock`을 재생성할 때 비활성 의존성의 별도 고정 Git/휠 소스에 접근할 수 있다. Hermes Agent upstream 저장소 fetch는 설치에 필요하지 않았다.

## 테스트 및 실측

| 검증 | 결과 |
|---|---|
| Clean Install | Windows CPython 3.14.7, 깨끗한 cache, Git 프로토콜 `never`. `AIAgent`와 CLI import 경로·메타데이터 판독. 활성 Core가 외부 엔진에서 전이 import하지 않는 절대 경로 검사 |
| 업데이트 / 롤백 | `0.1.0+iris.a382af23`에서 `0.1.1+iris.a382af23`으로 실제 갱신. 선택된 Ollama 모델 호환성 턴을 통과한 뒤 선택 전환. 이전 슬롯으로 롤백하고 신규 슬롯을 다시 선택 |
| Setup 검사 | `SetupProtocol.verify_core` 실제 Ollama 모델 턴 통과. Staging payload에 엔진, lock, manifest, 원본 라이선스와 provenance 포함 확인. Inno Setup 컴파일 성공, `43,494,419`바이트 로컬 검증 산출물. 전체 EXE 설치 흐름은 별도 검증 필요 |
| Reference 일반 턴 | PID `40512`, 준비 1.387초, 최종 17.375초, `IRIS-ACF-HELLO` |
| 첫 Owned 일반 턴 | PID `3800`, 준비 0.142초, 최종 7.465초, 같은 응답. 첫 격리 설치에서는 이전 `aiohttp` 검사와 무관하게 실제 `AIAgent` import를 확인한 후 실행. 최종 패키지는 엄격한 Ready probe와 별도 모델 검사 통과 |
| Control API | 인증, Action Catalog 및 실행 계약 점검 통과 |
| Unit / Integration | `unittest` 156개 통과. 활성 턴 처리 중 엔진 선택을 유지하고 다음 턴에서 변경을 반영하는 계약 포함 |
| Core / FPR 자검 | 30개 통과. Windows 프로세스 트리 취소 및 H1, Code Box, App Host, 스트리밍 렌더러 자검은 기본 샌드박스에서 실패한 뒤 Windows 소프트웨어 렌더링·프로세스 컨텍스트에서 통과 |
| Owned 실제 GUI | `gpt-oss:20b`, GUI PID `39992`, sidecar PID `47080`, `0.1.1+iris.a382af23`, SQLite 대화 `2` 착지 71.570초. 도구 요청 1건의 Host `shell.run` 라우팅 확인. 모델은 요청한 문자열 대신 일반 응답을 반환 |
| Owned GUI Provider 관측 | 첫 API `2,135` 토큰 / 37.5초, 후속 API `2,133` 토큰 / 1.3초. 위 GUI 한 건의 Provider 로그 값 |
| Owned GUI 재시험 | 16,384 컨텍스트 설정은 엔진의 최소 64,000 사전 검사에서 거부됨. 테스트 홈을 65,536으로 설정한 재시험에서 `shell.run`, `browser.open` 모두 IRIS Host 경로로 갔으나 결과는 실패였고 답변은 요청과 무관했다. SQLite 착지 128.129초 |
| Owned Desktop Control | 명시한 Shell 명령의 stdout에서 marker 확인. 합성 계정을 사용한 Email Compose가 수신자·제목·본문을 채우고 `sent=false`를 반환. 초기 초안 요청의 모달 대기를 수정하고 GUI에서 재실행 |

일반 턴은 동일 모델·Provider·프롬프트·Tool Schema를 사용했다. 길이가 짧아 `ContentDelta`가 관측되지 않았다. 각각 한 건의 준비/응답 시간으로 성능 변화율을 계산하지 않았다. 일반 턴의 토큰 수, 메모리, 오류 복구율 및 장시간 작업 실패율은 측정하지 않았다.

검증용 Setup EXE의 SHA-256은 `9be7d55b43b79a2ae8672f8d3a379fa82f0006503f68d38c4c58fd8f9950c1ae`이다. 별도 홈에서 엔진 설치 단계와 모델 호출을 직접 검증했다. 이 EXE는 로컬 컴파일 산출물이다.

| 사용자 시나리오 | 검증 상태 |
|---|---|
| 1 일반 대화 | Reference/Owned 동일 marker 실제 응답 |
| 2–3 Wiki → Browser | Browser intent 및 계약 확인. GUI 실제 연속 실행/재승인 미검증 |
| 4–5 Python/CWD, 30초 출력 | Workspace 환경과 실행 계약 확인. 실제 장시간 stdout/stderr·사용자 취소 미검증 |
| 6–11 IDE 경로 | Tool Schema, 실행 환경 및 patch 계약 확인. 실제 IDE Shell, dirty buffer 및 모델 편집 루프 미검증 |
| 12 Process start/status/read_output | 자동 계약 및 Owned Desktop Control로 세 작업 실행 성공. `echo` 출력 marker 확인. 실제 모델의 연쇄 동작은 미검증 |
| 13 Email draft | Owned Desktop의 합성 계정으로 실제 Compose prefill과 `sent=false` 확인. 계정 없는 경우 실패 응답 확인. 실제 모델 및 Reference의 GUI 초안·승인 동등성은 미검증 |
| FPR 추가 제품 기능 | Code Box, App Host, Streaming, H1·스크롤, 모델 목록 및 승인 카드 계약 확인. Owned Desktop에서 모델 피커가 열리고 앱이 동작한 상태를 확인. 즐겨찾기 보존과 실제 모델 변경은 미검증 |
| 외부 서비스/장치 | Calendar, Voice, Emulator, Aloha, Routine의 실제 계정·장치 별 동등성 미검증 |

## 복구 절차

앱의 Python에서 저장된 이전 슬롯을 검증한 후 다시 선택할 수 있다. 진행 중인 턴은 실행 중인 인터프리터를 유지하고 새 턴부터 선택을 반영한다.

```powershell
.venv\Scripts\python.exe -c "from iris.infrastructure.agent_runtime import iris_agent_home; from iris.system.iris_agent_install import rollback_iris_agent; print(rollback_iris_agent(iris_agent_home()))"
```

이전 슬롯의 준비·무결성 검증이 실패하면 명령이 이유를 반환한다. `iris-engine-selection.json`과 Agent Home `logs/iris-install-*`를 확인한 뒤 검증된 IRIS 설치 패키지에서 엔진 번들을 복구한다. 기존 엔진 디렉터리와 사용자 데이터는 복구 자료로 유지한다.

## 최종 감사

- 기존 `.audit`의 31개 추적 경로를 확인했다. 추적된 `.env`, Venv, `__pycache__`, 임시 테스트 홈, 지정된 설치 로그는 없었다. 제한된 추적 텍스트의 자격 증명 패턴 후보는 0개였으며 비밀값은 출력하지 않았다.
- **남은 P0** · 동일 조건 Reference/Owned의 사용자 13개 및 추가 FPR GUI 전수, `gpt-oss:20b`의 Live Tool 결과 실패와 무관한 후속 답변 원인, 실제 승인/거부/취소·IDE의 전수 증거, 기존 설치의 통제된 전환 및 Windows 설치 프로그램 완주 증거.
- 기존 Owned 설치가 손상된 경우의 자동 복구는 source/import/Sidecar 준비 검사를 사용한다. 모델 호환성 턴은 명시적 업데이트와 Setup 최종 검사에서 실행한다. 자동 복구 직전의 모델 턴 강제 조건은 남아 있다.
- **남은 P1** · Gateway/Control Sync·호환 shim 계층의 호출자 제거와 물리적 정리, 플랫폼별 설치 증거 및 미래 자산 실행 점검. 기존 원본 Web 도구 import에서 `plugins.web` 경고가 있었으므로 비활성 CLI·플러그인 자산을 검증 전 제거하지 않는다.
- [Wave 2 계획](iris-agent-unified-runtime-wave2-brief.md)과 [Wave 3 계획](iris-agent-unified-runtime-wave3-brief.md)은 유지했다. 커밋, 푸시, 배포 및 실제 사용자 설치 전환은 수행하지 않았다.
