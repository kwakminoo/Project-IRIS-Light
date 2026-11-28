# Wave 1.7 FFC-07 → MASTER 08 인수인계

2026-11-28 기준 FFC-07 **PARTIAL**. 자동 검사, L7 확장 계약, 격리된 Core 설치 수명주기, 로컬 Windows 패키지 빌드를 수행했다. 실모델 PDF 근거성 결함을 수정했다. GUI 작업의 반복 안정성은 별도 판정이 필요하다. 독립 검증은 MASTER 08 세션에서 진행한다.

## 기준선과 실행 환경

- HEAD `434081fd161f3b011d1897cc5791ccf7100de9c6`의 FFC 01–06 작업 트리를 보존했다. 최종 working-tree SHA-256 `5717572f990c61be6cd6add32e537ac1a82b72be468d533dab92a403f04ad9a5`는 `scripts.validate_wave17 inventory`의 4,140개 파일 해시 맵 기준이다. 기준선 Git blob의 UTF-8 BOM과 누락된 검색 경로 때문에 실패한 inventory를 수정한 뒤 심볼 감사까지 완료했다. 최종 변경 트리에 대응하는 CI 실행은 **UNVERIFIED**.
- 앱 Python 3.13.7. 활성 슬롯 `iris-agent.slot-272facc0f5fd4b6f`, 이전 슬롯 `iris-agent.slot-e38f3ea761714c36`. 활성 슬롯에서 `run_agent`, `iris_agent_cli.main`, `hermes_cli`를 실제 import했다. Python 3.14.7, Core `0.1.2+iris.a382af23`, MCP SDK 2.3.0, upstream `a382af23f4c067d23463b5781958684c2cda82bc`. vendor와 활성 슬롯의 manifest, lock, 실행 파일, MIT 및 provenance 바이트를 대조했다. `legacy_migration_approved=false`. 세부 해시는 `.tmp/ffc-07/runtime.json`.
- 실모델 `gpt-oss:20b`, loopback Ollama `:11434/v1`, advertised 131,072, tool capability 있음, sidecar 요청 64,000. 최종 PDF 시나리오 로그의 실제 loaded는 4,096, prompt 1,619, completion 167토큰이다. 모델 실행 중 독립 메타데이터 조회는 별도 증거다.
- Windows 호스트의 빌드 번호는 26200이다. 별도 클린 Windows 실행 환경이 확인되지 않아 Setup.exe의 신규 OS 설치·첫 실행은 **BLOCKED**. L6는 격리 홈에서 제품 Owned Core을 설치·업데이트·롤백한 결과다.

## 01–07 최종 상태

| 단위 | 판정 | 현재 증거와 남은 작업 |
| --- | --- | --- |
| 01 Product Recovery | PARTIAL | 기존 미설치/연결 복구와 선택 유지, 현재 FPR-13 Picker 및 스트리밍 통과. 실제 Ollama 창 적용과 모델 제거 후 앱 재시작 시나리오 미검증. |
| 02 Memory 및 Wiki | PARTIAL | SQLite 범위·revision·취소/승인과 L6 저장 복구 통과. 이번 GUI 재검은 저장, 새 대화 회상, 갱신, 설정 목록, 삭제, 삭제 후 미회상, Wiki 해시 유지 7/7 PASS. 과거 편차와 반복 검증을 별도로 남긴다. |
| 03 Functional Absorption | PARTIAL | 계약과 Todo 저장/복원 통과. 실모델 Todo/Clarify, Voice UX 및 외부 제공자별 실행은 증거가 부족하다. |
| 04 Gateway 및 MCP | PARTIAL | 현재 실제 Gateway SSE, 승인/결과, 재시작 후 세션·실행·검색, MCP 수명주기 통과. 별도 외부 계정 어댑터, 외부 OAuth, 공개 TLS 미검증. |
| 05 Agent 및 Document | PARTIAL | 실제 201쪽 PDF에서 87쪽만 읽고 표식을 정확히 반환했다. 수정 전 두 시도는 호스트 추출 성공 뒤 모델 응답에서 실패했다. Native/MCP/mixed 각각 10회는 미실행. |
| 06 Product Regression | PARTIAL | Windows pytest 및 전 FPR-13 시나리오 통과. 최종 GUI MCP, mixed 및 Shell은 성공했고 Native 단독 검색·읽기는 두 실행에서 모델이 도구를 호출하지 않았다. 초기에 Shell도 실패했다. 최종 실제 스트리밍 종료 PASS. FFC-06 과거 Process 10/10과 OCR 종료 증거를 보존했다. 실제 Voice/Todo/Clarify 및 IDE/Wiki/Voice 작업 중 종료는 미검증. |
| 07 Foundation Certification | PARTIAL | 새 Native 도구·Provider·MCP/Skill, 데이터 복사 및 슬롯 복구, 로컬 Launcher/Setup 빌드 완료. 핵심 GUI·문서 안정성 재검 및 클린 Windows 설치가 남았다. |

## 현재 실행 증거

아래 경로는 프로젝트 루트 기준이다. 로컬 로그에는 fixture 데이터와 요청 식별자가 있다.

| 계층·검사 | 결과 | 명령과 로그 |
| --- | --- | --- |
| L1–L6 FPR-13 | 고유 시나리오 25/25 PASS. 혼합 실행 24/25, 분리 제품 홈의 IDE 1개 추가 PASS(9/9 단계). | 앱 venv에서 `python -m iris.system._check_fpr13_runner --include-live --include-gui --include-lifecycle --out-dir .tmp/ffc-07/fpr13-final`, `python -m scripts.validate_wave17 gui-product-home --out .tmp/ffc-07/product-home-final`. 각각의 `results.json`, `logs/` 및 통합 `.tmp/ffc-07/fpr13-combined.json`. |
| Windows pytest | 1,299 PASS, 199 subtest PASS, 선택적 qwen-tts 1 SKIP, 0 FAIL/ERROR. | `QT_QPA_PLATFORM=windows`, `IRIS_WAVE17_LIVE=1`, `PYTHON_DOTENV_DISABLED=1`로 `python -m pytest tests -q --junitxml=.tmp/ffc-07/pytest-final.xml`. `pytest-final.log`. |
| L7 Native | `tool_describe` 발견, 고위험 1회 승인, 실행 표식과 tool_call ID 및 request ID 상관관계가 일치했다. 허용 목록과 레지스트리는 격리 프로세스에만 주입했고, 제거 후 미노출 및 기존 ping을 확인했다. | `python -m scripts.validate_wave17 foundation-native --out .tmp/ffc-07/native-final`. `foundation-native.json`, `agent/host-watch.log`, `agent/logs/agent.log`. fixture 초기 실패는 invoker 연결 및 범용 enum 검증 가정에서 발생했다. 핵심 스키마 타입 검사를 실행했고 액션별 enum 검증에 대한 범용 적용은 별개다. |
| L2/L3 Provider | Ollama NDJSON과 OpenAI 호환 SSE 정상 종료·본문 오류·조기 닫기 테스트 PASS. 등록된 loopback API 행을 통한 Owned Core SSE 두 요청에서 Native ping 스키마, 분할 도구 인수와 동일 결과 ID, 두 청크 및 최종 응답이 통과했다. | `python -m pytest -q tests/test_wave17_foundation_provider.py tests/test_wave17_adaptive_context.py`. `run-provider-owned-verified.py` 및 `.tmp/ffc-07/provider-owned-verified/result.json`. |
| L7 MCP·Skill | 실제 stdio 등록 및 모델 발견·승인·실행·업데이트·비활성·제거. MCP 멀티 서버 재연결 및 구형 바인딩 거절, 승인된 Skill 생성·열람·수정·비활성·보관 PASS. 별도 로컬 확장 설치 fixture PASS. | `python -m scripts.validate_wave17 mcp --out .tmp/ffc-07/mcp`, `python -m iris.mcp._check_multiserver_reconnect`, `test_wave17_skill_tools.py`, `.tmp/ffc-07/extension-fixture.log`. |
| L4 Gateway | 실제 모델 및 MCP 승인, SSE 이벤트, 재시작 후 세션·실행·검색 PASS. | `python -m scripts.validate_wave17 gateway-mcp --out .tmp/ffc-07/gateway`. `gateway-result.json`. |
| L6 데이터·슬롯 | 구형 채팅 SQLite 복사본에서 대화·텍스트 포맷을 유지했다. 태스크·메모리·세션·첨부·Gateway 이벤트·MCP 설정을 업데이트 및 손상 복구 후 다시 검사했다. 원본 복사 기준 DB 해시 유지. 새 슬롯, 후보, 업데이트 후, 롤백 후 실모델 총 4회 PASS. | `python -m iris.system._check_foundation_data`, `python -m iris.system._check_owned_lifecycle`를 FPR-13에서 실행. `.tmp/wave16-lifecycle/run-m8vigc7v/evidence.json`. |
| L4/L5 제품 실모델 | 최종 GUI MCP, 혼합 파일+MCP, Shell, 스트리밍 중 창 닫기 PASS. 독립 Native 검색→읽기 PASS 및 GUI Memory 7/7. 단독 GUI Native 검색·읽기 FAIL. PDF 201쪽 실제 모델의 87쪽 표식 일치. | `python -m scripts.validate_wave17 gui-chat --product-tools --out .tmp/ffc-07/gui-tools-final`, `gui-chat --shutdown-stream --out .tmp/ffc-07/gui-shutdown-final`, `gui-chat --product-memory --out .tmp/ffc-07/memory`, `native --out .tmp/ffc-07/native-file`, `.tmp/ffc-07/run-document-final.py` 및 `document-final/result.json`. |

문서 모델 응답의 첫 두 실패를 `document-verified/result.json`, `document-retry/result.json`에 보존했다. 기존 도구는 원본 PDF 상태와 함께 미열람 200개의 행까지 모델에 반환했다. `iris/engine/runtime.py`가 모델로 보내는 `content.extract` 성공 결과에서 미열람 행을 집계하고 실제 처리 상태와 오류를 보존한다. 최초 회귀 검사는 실패했고 수정 후 통과했다. 원본 형식은 별도 직접 호출과 GUI에서 유지된다. 실모델 수신 도구 결과는 13,740자에서 668자로 줄었다. 최종 실모델 두 시도에서 87쪽 표식 `IRIS-FFC05-P087-VAL=867668`이 일치했다. 두 번째는 실패를 재현한 원래 요청과 같았다. `.tmp/ffc-07/document-final/result.json`, `.tmp/ffc-07/document-same-prompt/result.json`.

## 설치 파일과 레거시 경로

PyInstaller 6.22.2로 `python -m PyInstaller --noconfirm --clean IRIS.spec`, Inno Setup으로 `scripts/build_iris_setup.ps1 -NoPublish`를 격리한 소스 스냅샷에서 실행했다. 첫 Setup 스테이징에서 컴파일 입력 `installer/InfoAfter.txt`가 누락됐다. 입력을 포함해 재빌드했고 PDF 수정 뒤 Launcher와 Setup을 새 경로에서 다시 빌드했다. `payload-final.log`에 작업 트리의 최종 런타임과 패키징 입력의 일치, Core 검증과 제외 규칙을 남겼다. 이번 인증 문서는 빌드 스냅샷 밖에 있다. 이 설치 파일은 로컬 검증용이며 서명이나 공개 릴리스는 수행하지 않았다.

| 아티팩트 | 바이트 | SHA-256 |
| --- | ---: | --- |
| `.tmp/ffc-07/package-final/dist/IRIS.exe` | 8548081 | `6c4c220d2b741aeaf8c199f5a6616ad6cfa68cceb8a0cf134e617223f7ddea5e` |
| `.tmp/ffc-07/package-final/dist/IRIS-Setup.exe` (0.1.18) | 42675324 | `9b5efb38935aa75653635aad632611c98ff863e29549df9c23027c872c38e798` |

스테이징 입력 지문 `98cd9d6f34a5c15c4ec58cbf102af49e99486ca990bd8a8ceb40e5a610f9bbe8`. `.tmp/ffc-07/package-source-final.json`, `package-sha256-final.json`, `launcher-final.log`, `setup-final.log`.

| 레거시 | 현 상태와 확인한 호출자 |
| --- | --- |
| `iris/system/iris_agent_gateway.py`, `:8642` | `agent_runtime.ensure_iris_agent_runtime`에서 Gateway 기동은 명시 옵트인. `setup_protocol.py`, `setup_wizard.py`, `iris_agent_install.py`, `iris_agent_client.py`, Ollama guard에 진단·복구·경로 호출이 있다. Desktop의 정상 실행은 InternalSidecar이며 실제 GUI에서 이전 Gateway 없이 스트리밍했다. |
| vendor `gateway/` | Owned vendor의 공식 CLI 및 게이트웨이 플랫폼 호출이 남아 있다. 제품의 Native Gateway는 `iris/system/native_gateway.py`와 Control Surface가 담당한다. |
| `hermes_cli` reverse shim | vendor shim이 `iris_agent_cli`로 포워딩한다. `_sidecar_main.py`의 읽기 전용 설정 import와 활성 슬롯 실제 import를 확인했다. |
| `integrations/hermes-*` / `hermes-plugins` | Control Sync에 MCP/Skill 경로, Soul Sync에 Soul 경로가 있다. SerpAPI 플러그인은 현재 정상 경로 호출자가 확인되지 않았으며 `integrations`를 복사하는 설치 패키지에 남는다. 호환 및 패키지 변경의 동등성 증거를 확보한 뒤 정리 대상이다. |
| `absorbed_toolsets` overlay | overlay 적용 코드는 기존 검사가 직접 참조한다. 현재 설치된 소스와 프로덕션 wire가 사용되는 동안 복구/참조 자산으로 유지했다. |
| `scripts/apply_env_to_hermes.ps1` | 파일은 퇴역 상태. 제품 호출자가 없으며 문서와 부재 회귀 검사만 참조한다. |
| 전역 sidecar 탐색/종료 | `_kill_stray_sidecars`와 전용 PID 보조 함수의 사용처가 없었다. 제거 후 제품 미기동 검사, 소유 child 생명주기 및 L6를 통과했다. |

독립 확인 대상은 반복 모델 근거성, 실제 작업별 종료 취소, 리소스와 모델 런타임 Context 실효치, 별도 클린 Windows의 Setup·첫 실행이다. 복구 Reference와 MIT/provenance는 검증된 소스와 payload에 보존했다.
