# IRIS Wave 1.7 독립 검증

2026-11-27 KST · Windows x64 · **Wave 2 NO-GO**

## 1. Independent Validation Report

검증 시작 시 HEAD는 기준선과 같은 `a6927b12537a507e66f8a20f447f1a5ffd7df5aa`였다. 기능 마감 구현은 워킹 트리에 있었다. 시작 지문은 `c59a27150898551ba2e787605e0f487f0777de4363338adb7c13beff2b831c1d`이며, 기준선 대비 4,100개 소스 파일의 해시와 변경된 Python 함수·클래스 207개의 범위를 기록했다. 이번 검증 중 수정한 파일과 최종 지문은 빌드 증거에 있다. 그래피파이는 사용하지 않았다. [시작 소스](../../.tmp/wave17-final-independent-20261127/inventory-start/source.json) · [변경 정의](../../.tmp/wave17-final-independent-20261127/inventory-start/symbols.json) · [초기 Git 상태](../../.tmp/wave17-final-independent-20261127/git-status-start.txt) · [최종 빌드·소스](../../.tmp/wave17-final-independent-20261127/build-source.json)

앱 Python 3.13.7에서 활성 Owned Core를 선택했다. Core 버전은 `0.1.2+iris.a382af23`, 슬롯은 `iris-agent.slot-272facc0f5fd4b6f`, Python은 3.14.7, MCP SDK는 2.3.0이었다. 실제 `AIAgent`는 활성 슬롯의 `run_agent.py`에서 import됐다. 설치된 Core와 Vendor의 `SOURCE_MANIFEST.json`, `uv.lock`, `run_agent.py`는 SHA-256이 일치했다. 이전 슬롯은 `iris-agent.slot-e38f3ea761714c36`의 `0.1.1+iris.a382af23`였다. GUI와 로컬 Gateway는 체크아웃의 호스트 코드와 이 Core를 실행했다. 최종 소스 지문은 `b95b21a34dc3a69ec4d9d4d5ff0743c99e1002245a9a57b89814157542d71962`다. [런타임 증거](../../.tmp/wave17-final-independent-20261127/runtime.json)

아래 명령은 저장소 루트에서 앱 `.venv/Scripts/python.exe`로 실행했다. pytest 9.0.3은 기존 사용자 패키지 경로에서 불러왔다. L1은 소스·설치 확인, L2는 계약, L3는 실제 로컬 프로토콜, L4는 실제 Owned 모델 또는 제품 Control, L5는 실제 Windows GUI, L6는 격리 설치 환경이다. 각 결과 파일에 시나리오별 명령이나 입력, 실행 시간, 시도 수와 판정이 있다. 같은 표의 결과는 별도 지문이 명시된 경우 외에는 이 체크아웃과 위 Core 버전에 적용된다.

## 2. Functional Absorption Matrix

| 기존 Hermes 기능 | IRIS 진입점 및 관찰 | 상태 |
|---|---|---|
| vision_analyze | 첨부 ID를 기반으로 한 `vision.analyze`. 로컬 Vision 제한 소스·계약 확인. 실제 Vision 모델 응답 대기 | PARTIAL |
| image_generate | 일상 제품 모델 턴의 IRIS 이미지 생성 바인딩과 Provider 실행 증거 없음 | UNVERIFIED |
| skills_list | 공용 스킬 목록, 등록된 항목 조회 계약 | PASS L2 |
| skill_view | 등록된 스킬 본문 읽기 계약 | PASS L2 |
| skill_manage | 공용 프로필의 추가·상태 변경과 사용자 승인 계약 | PASS L2 |
| text_to_speech | 제품 음성 경로가 있다. 모델 바인딩·실제 재생 및 취소 증거 없음 | PARTIAL |
| todo_list | 계획·실행·완료가 일치하는 실제 모델 턴 증거 없음 | UNVERIFIED |
| memory | IRIS 대화와 검색, Owned 상태의 계약 확인 범위. 모델 작성·변경 후 세션을 넘긴 회수 대기 | PARTIAL |
| session_search | Gateway 주체별 대화 검색을 실제 재시작 뒤 검증 | PARTIAL |
| clarify | 대기·사용자 응답·턴 재개를 끝까지 수행한 모델 결과 없음 | UNVERIFIED |
| execute_code | 셸의 실제 모델 turn·Native 승인 fixture·격리 프로세스 결과가 있다. 별도 코드 실행 기능 전체 대체 대기 | PARTIAL |
| delegate_task | Engine과 Worker 소스 경로 존재. 권한 상속·예산·깊이·자식 종료 실모델 재현 대기 | UNVERIFIED |
| cronjob_manage | Routine 및 실행 계약 범위. 실모델 등록·취소·재시작 복구 대기 | PARTIAL |
| computer_use | Browser와 IDE의 개별 제품 검사. 범용 컴퓨터 사용 도구 계약·실모델 전 과정 대기 | PARTIAL |
| manage_connections | MCP 설정 계약 범위. Connector, 계정 연동과 재연결 대기 | PARTIAL |

등급은 확인한 계층에 적용된다. 계획, 메모리 압축, 플러그인 Hook 수명주기, 권한 상속 및 추가 Hermes Conversation Loop 분기의 완전한 흡수는 UNVERIFIED다. [스킬 및 턴 계약](../../.tmp/wave17-final-independent-20261127/gateway-mcp-focused.log) · [기존 기능 대응표](wave17-fc-functional-absorption.md)

## 3. Gateway & MCP Validation Matrix

| 시나리오 | 계층 및 기대 | 실행 및 결과 | 판정 |
|---|---|---|---|
| Gateway 시작·인증·영속성 | L3/L4. 인증된 모델 응답, 재시작 뒤 본인 세션·실행·검색 가능 | `-m scripts.validate_wave17 gateway-restart` 1회. 준비 503→200, 무토큰·오토큰 401, 소유 세션과 Run 모두 200, 본인 검색 성공. 중지 약 0.308초. 기준선의 404·404가 해결됐다. 간단한 응답은 최종 NDJSON 이벤트만 관찰했다. [결과](../../.tmp/wave17-final-independent-20261127/default-gateway-restart/gateway-result.json) | PASS |
| Gateway 실모델 MCP·승인·스트리밍 | L4. Scope 토큰으로 MCP 요청, Control 승인, 고유 값 응답, 저장·재검색 | `-m scripts.validate_wave17 gateway-mcp` 1회, 12,288 컨텍스트. Scoped 토큰의 승인 시도 401, Control 사용자 승인 200. 실제 서버의 고유 값을 답했고 승인 이벤트·delta·최종 응답을 수신했다. 재시작 뒤 소유 Session/Run은 200, 소유 검색 성공. 호환 토큰에는 해당 세션 404와 빈 검색 결과. [실측](../../.tmp/wave17-final-independent-20261127/isolated-gateway-mcp/gateway-result.json) | PASS |
| Gateway 범위·승인 | L2/L3. 주체별 세션·토큰 상태·승인 정책 | `pytest tests/test_wave17_native_gateway.py tests/test_wave17_control_surface.py`. Scope, 발급·만료·회전·폐기, Control 승인과 소유 분리 계약, HTTP 비활성/바인딩 실패에도 Native Registry 유지. 범위에는 부하·Crash·서명 Webhook·Connector 검증이 남았다. [집중 회귀](../../.tmp/wave17-final-independent-20261127/gateway-mcp-focused.log) | PARTIAL |
| STDIO | L3. 초기화, 두 페이지의 도구 조회, 현재 스키마 확인, 실제 호출·리소스·프롬프트 | `pytest tests/test_wave17_native_mcp.py`. 실제 Owned SDK. 도구는 구조화 코드 42, 리소스와 프롬프트는 각각 고유한 fixture 문자열을 반환했다. [집중 회귀](../../.tmp/wave17-final-independent-20261127/gateway-mcp-focused.log) | PASS |
| Streamable HTTP·SSE | L3. 실제 초기화·발견·호출·인증 전달 | 각각 독립 발견 1회·호출 1회. 등록 서버가 그 세션의 고유 값으로 응답했고 결과와 호출 목록을 대조했다. [집중 회귀](../../.tmp/wave17-final-independent-20261127/gateway-mcp-focused.log) | PASS |
| MCP 타임아웃 | L3. 초기화 지연 시 제한 시간 반환 | `-m scripts.validate_wave17 mcp-timeout` 1회. 5.547초 후 `timeout` 반환, 도구 실행 여부 불확실 플래그는 false. [실측](../../.tmp/wave17-final-independent-20261127/mcp-timeout/mcp-timeout.json) | PASS |
| MCP 호출 중 취소 | L3. 실제 STDIO 도구 진입 후 취소하고 서버 프로세스 회수 | `mcp_cancel_probe.py` 1회. `cancelled`와 실행 여부 불확실 플래그를 반환했고, 기록한 서버 PID는 3.106초 시점에 종료돼 있었다. 네트워크 단절 조합은 미검증이다. [실측](../../.tmp/wave17-final-independent-20261127/mcp-cancel/result.json) | PASS |
| Native/MCP 표면 | L2. 등록·활성·스키마·실행 권한이 Host와 Sidecar에 일관 적용 | `-m iris.engine._check_tool_surface`, 집중 pytest. 등록·비활성화·인수·스키마 지문·설정 변경·승인·실행 시 동일 바인딩 조회 계약. Eager/Deferred와 검색·상세·실행의 실제 모델 반복은 부분 확인. 동시 외부 호출은 UNVERIFIED. [Tool Surface](../../.tmp/wave17-final-independent-20261127/iris.engine._check_tool_surface.log) · [집중 회귀](../../.tmp/wave17-final-independent-20261127/gateway-mcp-focused.log) | PARTIAL |
| MCP 제품 GUI | L5. 실제 등록·상태 표시·사용 선택 | `mcp_gui_probe.py` 1회. Windows GUI의 추가·사용 버튼을 클릭했다. 저장 확인과 상태 점이 표시됐고, 등록된 서버에서 도구도 탐색했다. 제품 GUI에서 승인 버튼을 거쳐 모델 최종 응답까지 이어진 한 번의 실행은 미검증이다. [GUI 실측](../../.tmp/wave17-final-independent-20261127/mcp-gui/result.json) | PARTIAL |

## 4. Agent Quality Benchmark

모델은 `gpt-oss:20b`, 선택 정책은 `auto`였다. Ollama 기본과 격리 서버를 같은 모델로 각각 검사했다. MCP는 실제 서버에 기록된 UUID 한 개를 답변이 정확히 복사해야 통과한다. 파일 탐색은 정확한 본문 답변과 성공한 `local.search_files → local.read_file` 호출 순서를 요구했다. 정상 결과까지 복구하면서 실행한 재시도나 중복 호출도 원본에 남겼다. 독립 시도마다 Core 홈·파일·서버 또는 세션을 새로 만들었다. [러너](../../scripts/validate_wave17.py)

| 시나리오 | 이전 `a6927b1` | 이번 결과와 근거 |
|---|---|---|
| A. 파일 탐색→읽기 | 0/10 | 기본 서버 0/1. 확대 컨텍스트 9/10. 10회 답변이 실제 파일과 일치했고, 1회에 불필요한 중복 읽기가 있어 실행 순서 기준에서 실패했다. 7회에서 Host가 거부한 호출이 있었고 3회는 거부 없이 통과했다. [기본](../../.tmp/wave17-final-independent-20261127/default-native/native-results.json) · [격리](../../.tmp/wave17-final-independent-20261127/isolated-native/native-results.json) |
| B. 파일 탐색→수정→실행 | UNVERIFIED | 셸과 IDE 개별 실행 PASS. 모델이 일련의 쓰기와 실행을 끝낸 증거는 UNVERIFIED |
| C. Native→MCP | UNVERIFIED | 격리 표본 3/5. 5회 모두 파일과 MCP의 고유 값을 반환했고, 2회는 성공한 호출 순서가 뒤바뀌었다. [격리](../../.tmp/wave17-final-independent-20261127/isolated-mixed/mixed-results.json) |
| D. 복수 MCP 호출 | 0/6 MCP 기본 | 기본 서버 0/1, 격리 5/6. 격리 6회 모두 실서버 호출, 1회 답변에 UUID 끝 두 글자가 빠졌다. 복수 MCP 서버 순차·동시 완료는 UNVERIFIED. [기본](../../.tmp/wave17-final-independent-20261127/default-mcp/mcp-results.json) · [격리](../../.tmp/wave17-final-independent-20261127/isolated-mcp/mcp-results.json) |
| E/F. Browser→저장, IDE→수정·실행 | PARTIAL | Browser GUI와 제품 IDE 각각 PASS. 모델이 Browser와 IDE 작업을 주도하는 전 과정은 UNVERIFIED |
| G/H/I/J. 계획, 메모리, Clarify, 위임 | UNVERIFIED | 전체 모델 턴 실행 증거 없음 |
| K/L. 오류 복구, 장시간 취소 | PARTIAL | 자연어 파일 검사에서 인수 수정과 결과 복구 관찰. 실제 장시간 모델 작업의 취소 및 후속 실행은 UNVERIFIED |
| M/N. PDF 페이지 추가 읽기, OCR 복합 | UNVERIFIED | 일반 PDF와 OCR PDF는 기본 모델 각각 1/1. 201쪽 추가 읽기는 1회 모델이 파일명을 ID로 적은 도구 호출 형태의 텍스트를 답해 FAIL. 초기 두 번은 테스트 호스트 구성 실패로 따로 보관했다. OCR→학습/쓰기 같은 복합 후속 도구는 UNVERIFIED. [텍스트 PDF](../../.tmp/wave17-final-independent-20261127/owned-provider/text-result.json) · [OCR PDF](../../.tmp/wave17-final-independent-20261127/owned-provider/ocr-result.json) · [201쪽](../../.tmp/wave17-final-independent-20261127/owned-provider-deep-final/deep-result.json) |

기본 Ollama와 별도 서버 12,288 환경은 독립 집계했다. 다른 설치 모델과 비교, 장기 부하, 모든 시나리오의 5회 반복 검증은 남아 있다. [실측 집계](../../.tmp/wave17-final-independent-20261127/result-summary.json) · [Ollama 컨텍스트 설정](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size)

## 5. Document Intelligence Validation Matrix

| 시나리오 | 계층·기대·결과 | 판정 |
|---|---|---|
| PDF 경로 경계 | L2/L3/L4. 기준 커밋의 합성 PDF에 `Attachment path`가 포함된 실패를 재현했다. 현재 `Attachment.payload()`, `PreparedAttachments.model_content(question)`, `inference_messages(history)`, 대화 저장/복구, 실제 로컬 Provider에 전송한 Owned Core HTTP 요청의 문서 메타데이터에서 첨부 절대 경로가 없었다. 합성 텍스트 PDF와 OCR PDF의 원문 값을 모델이 각각 재현했다. [기준선](../../.tmp/wave17-final-independent-20261127/baseline-attachment.log) · [Owned Core 전송 본문](../../.tmp/wave17-final-independent-20261127/owned-provider/text-request-01.json) · [OCR 전송 본문](../../.tmp/wave17-final-independent-20261127/owned-provider/ocr-request-01.json) | PASS 범위 확인 |
| 파일·대화 연결 | L2/L3. 첨부 ID가 대화에 저장되고 전환 후 복구된다. 다른 대화의 ID를 거부한다. PDF 추가 추출, IDE 첨부, 드롭과 여러 첨부의 경로. 첨부 폴더의 모든 Windows Junction 조합과 외부 Provider 전수는 미검증. [현재 회귀](../../.tmp/wave17-final-independent-20261127/ocr-focused.log) | PARTIAL |
| 실제 문서 | L3. `document_probe.py`로 텍스트, 영어·한글 래스터, 혼합, 빈 문서·빈 이미지, 암호, 손상, 짧은 제목·숫자, 페이지 범위를 1회씩 검증. 성공한 페이지와 실패 상태가 함께 보존됐다. [실측](../../.tmp/wave17-final-independent-20261127/documents-final.json) | PASS |
| OCR 오류 분류 | L3 및 L2. 합성 손상 언어팩을 `OCR_TESSDATA_INVALID`, 언어 누락을 `OCR_LANGUAGE_MISSING`으로 반환. Windows 설치를 변경하지 않고 임시 tessdata를 사용했다. 제어된 자식 프로세스에서 처리 중 취소 약 0.35초, 타임아웃 약 12.11초, 일반 오류 종료 코드 3을 기록하고 세 자식을 모두 회수했다. PDF OCR 실행 경로는 직접 Tesseract를 사용한다. 실제 Vision Provider는 미검증이다. [수정 전](../../.tmp/wave17-final-independent-20261127/documents-before.json) · [수정 후](../../.tmp/wave17-final-independent-20261127/documents-final.json) · [자식 프로세스](../../.tmp/wave17-final-independent-20261127/ocr-process.json) · [Tesseract 한국어 데이터](https://github.com/tesseract-ocr/tessdata_fast) | PARTIAL |
| 품질·성능 | 페이지별 지표와 전체 초 단위 실측, 텍스트 빠른 경로, 짧은 텍스트, 일부 페이지 성공 보존. 역순 범위는 기존 계약에 따라 순서를 정규화한다. 캐시 무효화·최대 메모리·진행 중 취소 지연·장문 OCR은 미검증. [실측](../../.tmp/wave17-final-independent-20261127/documents-final.json) | PARTIAL |

## 6. Compatibility & Caller Audit

| 표면 | 결과 |
|---|---|
| Python 정적 정의·호출자 | 변경 정의와 `rg` 호출 참조를 기준선과 대조했다. `content.extract`, 첨부 저장/복구, Gateway 인가·스토리지, Host→Sidecar와 UI Worker의 주요 호출이 실제 회귀에 진입했다. 외부 Plugin과 이전 DB 버전 전체 조합은 미검증이다. [변경 정의](../../.tmp/wave17-final-independent-20261127/inventory-final/symbols.json) · [참조](../../.tmp/wave17-final-independent-20261127/inventory-final/symbol-references.txt) |
| 레거시 Gateway | 제품 정상 기동, Gateway 단리 및 폐기 표면 3개 계약 PASS. 정상 모델 턴은 실제 Owned Core를 사용했다. 복구·진단 경로와 Vendor 유래 코드는 남아 있다. [레이어 검사](../../.tmp/wave17-final-independent-20261127/iris.system._check_gateway_legacy_isolated.log) |
| Qt·IDE | 실제 Browser 및 IDE 제품 흐름 PASS. IDE 첫 리포트가 CP949에서 출력 오류를 냈고 UTF-8 재검은 통과했다. 레거시 Qt `_log` 단언 21개는 기준선에서도 동일하게 실패한다. [IDE](../../.tmp/wave17-final-independent-20261127/product-home-utf8/logs/ide_product_control.log) · [기준선 비교](../../.tmp/wave17-final-independent-20261127/baseline-qt.log) |

## 7. Security Audit

Gateway 루프백과 합성 자격증명, 권한 있는 세션과 승인 소유자, 읽기/실행 구분, Desktop Native 권한 계약, MCP 등록·설정·스키마, 대화 첨부 소유자를 확인했다. 차단 경로는 기존 정상 API의 거부와 소스 정책 확인 범위로 진행했다. 공격 재현이나 우회 절차가 필요한 항목은 미검증이다. 플러그인 및 자식 에이전트의 권한 전파, 외부 Provider와 실제 계정의 비밀 노출 여부, 장시간 작업 중복과 전송 장애 조합은 UNVERIFIED다. [Gateway·MCP 계약](../../.tmp/wave17-final-independent-20261127/gateway-mcp-focused.log) · [실행 정책](../../.tmp/wave17-final-independent-20261127/iris.system._check_execution_policy.log) · [빌드·소스 스캔](../../.tmp/wave17-final-independent-20261127/build-source.json)

## 8. Product Regression Report

| 제품 범위 | 결과 |
|---|---|
| FPR13 | `--contracts-only`의 제한 실행은 15 PASS·2 FAIL. 같은 런타임 및 Transcript 검사는 실제 Windows 실행에서 각각 종료 코드 0. `--include-live --include-gui --include-lifecycle`는 24 PASS·1 UNVERIFIED. `--product-home`의 UTF-8 재검에서 IDE Control PASS. 최종 소스의 `--include-gui` 재실행은 19 PASS·6 UNVERIFIED. [계약 최초](../../.tmp/wave17-final-independent-20261127/fpr13-contracts/results.json) · [실행/수명주기](../../.tmp/wave17-final-independent-20261127/fpr13-live-gui-lifecycle/results.json) · [제품 홈](../../.tmp/wave17-final-independent-20261127/product-home-utf8/results.json) · [최종 GUI](../../.tmp/wave17-final-independent-20261127/fpr13-final-gui/results.json) |
| NIP-12 | 기존 55개 실행 명령을 재생했다. 54 PASS 및 1개 OCR 신호 검사 실패. 이미 없어진 내부 함수명 단언을 Tesseract의 실제 subprocess 실행 인자 계약으로 교체해 17개 unittest를 재통과했다. Launcher와 KEEP은 빌드·매니페스트에서 각각 검증했다. [최초](../../.tmp/wave17-final-independent-20261127/nip12/results.json) · [수정 후](../../.tmp/wave17-final-independent-20261127/nip12/no-console-repaired.log) |
| 전체 `python -m pytest tests` | 최초, Qt bootstrap, 최종 단일 프로세스 실행은 스크롤 검사에서 `0xC0000409`. 최종 소스의 139개 파일은 모두 분리 실행했다. JUnit 1,483건에서 실패 36건·건너뜀 2건. 배치 재분할 전 중단 4건은 집계에서 보존했다. 과거 `_log` 검사, IDE mock 호출부, Hermes 진단, 모델 선택, 음성 UX 등이 남았다. lock 단언은 해당 배치에서 실패했고 독립 실행에서는 통과했다. [최종 단일 프로세스](../../.tmp/wave17-final-independent-20261127/full-pytest-final.log) · [최종 분리 실행](../../.tmp/wave17-final-independent-20261127/pytest-shards-final/results.json) · [lock 재검](../../.tmp/wave17-final-independent-20261127/lock-final-standalone.log) |
| 실제 승인 GUI | 첫 5/5. 최종 소스의 계측 반복 3/5, 2회는 Skip 클릭 전에 승인 링크 표시 대기에서 타임아웃됐다. Transcript 준비를 확인한 진단에서는 3/3 통과했다. 이 차이가 제품과 테스트 중 어느 쪽에 있는지는 확정하지 못했다. 성공 시 Skip은 프로세스 미기동. Run은 승인 소비·상태 running→completed·프로세스 종료 0·실제 stdout·결과 파일로 확인했다. [첫 실행](../../.tmp/wave17-final-independent-20261127/process-gui-1.log) · [최종 승인 ID 및 클릭](../../.tmp/wave17-final-independent-20261127/process-confirm-trace-1.json) · [타임아웃 4회차](../../.tmp/wave17-final-independent-20261127/process-confirm-trace-4.log) · [타임아웃 5회차](../../.tmp/wave17-final-independent-20261127/process-confirm-trace-5.log) · [Transcript 준비 진단](../../.tmp/wave17-final-independent-20261127/process-confirm-trace-warm-1.json) |
| Chat·Attachment·Qt | 초기 실모델의 응답·스트리밍과 DOM 복원은 통과했고, 프로세스 종료에서 `0xC0000409`가 재현됐다. 활성 제목·Wiki 스레드가 정리될 때까지 종료를 보류하도록 수정했다. 수정 후 실제 GUI 2/2에서 스트리밍과 대화 복원, 프로세스 종료 0을 확인했다. 계측 실행에서는 종료 직전 창 소유 스레드가 모두 멈췄다. Wiki 요약이 진행 중이면 종료가 지연될 수 있다. 테스트 전체 묶음과 별도 IDE 혼합 묶음의 네이티브 중단은 남았다. [초기 진단](../../.tmp/wave17-final-independent-20261127/gui-thread-detail.log) · [종료 수정 실측](../../.tmp/wave17-final-independent-20261127/gui-thread-detail-fixed.log) · [계측 없는 재검](../../.tmp/wave17-final-independent-20261127/gui-chat-final-repeat/gui-chat.json) · [첨부 독립 회귀](../../.tmp/wave17-final-independent-20261127/qt-attachments-core-standalone.log) |
| 나머지 제품 | Home·HUD·Transcript·Workspace·Model Picker·Settings는 실행 범위별 계약 및 Desktop 검사. 실제 메일 계정, 캘린더 이벤트 생성, Voice end-to-end, Android Emulator, Aloha, 외부 플러그인 수명주기와 Monitor 부하는 UNVERIFIED. [전체 검사 목록](../../.tmp/wave17-final-independent-20261127/pytest-shards/results.json) |

## 9. Build & Lifecycle Evidence

Owned 슬롯 L6는 외부 Hermes CLI를 제외한 격리 홈에서 `uv sync --locked` 기반 첫 설치, 실제 모델 네 턴, 업데이트·손상 감지·롤백·합성 사용자 데이터 보존을 통과했다. 별도 Windows 클린 OS의 전체 Setup/사용자 마이그레이션은 BLOCKED다. [슬롯 수명주기](../../.tmp/wave17-final-independent-20261127/fpr13-live-gui-lifecycle/logs/installer_lifecycle.log)

PyInstaller thin Launcher와 Inno Setup 6.7.3의 0.1.18 패키지를 별도 작업 폴더에 빌드했다. 최종 패키지는 43,648,860바이트, SHA-256 `73b824bf8023cf125db5e0e9454ba86a271ccdc4e81f1cea4039f34aae934d94`다. 소스와 번들의 Python 파일 3,248개가 일치했고 컴파일 오류는 0개였다. 제3자 고지 해시와 제한된 비밀패턴 스캔 결과는 기계 판독 증거에 있다. 서명은 `NotSigned`였고 이 워킹 트리 소스의 CI 상태는 UNVERIFIED다. [Launcher](../../.tmp/wave17-final-independent-20261127/launcher-build.log) · [최종 Setup](../../.tmp/wave17-final-independent-20261127/setup-build-final.log) · [해시 및 소스 대응](../../.tmp/wave17-final-independent-20261127/build-source.json)

## 10. Wave 2 Entry Verdict

| 번호 | 진입 조건 | 상태 |
|---|---|---|
| 1–3 | Owned 단일 런타임, 외부 Hermes 없이 실행, 레거시 Gateway 정상 경로 폐기 | PASS · 확인한 루프백·Desktop·Owned 슬롯 범위 |
| 4–6 | Gateway 세션·실행 영속성, 주체별 권한, 도구·승인 | PASS · 루프백의 실제 모델·승인·주체 분리·재시작 범위. 연결 장애와 부하 전수는 Gateway 표 참조 |
| 7–9 | 모델 MCP 실행, 통합 Registry와 Policy | PARTIAL · 실제 호출 회복, 기본 설정 실패와 결과 정확도 편차 |
| 10 | 기존 기능의 검증된 대체 | PARTIAL · 흡수표 참조 |
| 11–12 | Multi-tool과 Multi-step | PARTIAL · 기본 모델에서 파일 탐색 실패, 반복 완결 미충족 |
| 13 | Memory·Planning·Delegation | UNVERIFIED · 전체 작업 실모델 증거 부족 |
| 14–15 | 첨부 ID 및 자동 절대 경로 차단 | PARTIAL · 확인한 대화·로컬 직렬화는 PASS |
| 16 | 실제 OCR 및 세부 오류 | PARTIAL · 한·영 인식과 누락/손상 판정 PASS, 남은 오류 조합은 문서 절 참조 |
| 17 | 핵심 Qt 종료 안정성 | PARTIAL · 실제 Chat 종료는 수정 후 PASS. 여러 Qt 검사의 단일 프로세스 종료 오류는 잔여 |
| 18 | 승인 GUI 반복 | PARTIAL · 최초 5/5, 최종 계측 3/5 |
| 19 | 호출자와 제품 호환 | FAIL · 분리 회귀 실패가 남아 있다 |
| 20 | 독립 설치·업데이트·복구 | PARTIAL · Owned 슬롯 L6 PASS, 전체 Windows Setup BLOCKED |
| 21 | 최신 소스 회귀 | FAIL · 전체 pytest 미완주와 분리 실패 |
| 22–23 | 미해결 P0 및 기반 P1 없음 | FAIL · 모델 반복성과 Qt 종료의 핵심 판정 미충족, 권한·흡수 전체 범위 미검증 |

Wave 2 개발 진입 게이트는 **NO-GO**다. 기본 모델 환경의 도구 완료 실패, 승인 카드 간헐 타임아웃, Qt 묶음 중단과 분리 회귀 실패, 201쪽 추가 읽기 실패 및 핵심 계획·위임 검증 공백이 남았다. Production Readiness, Public Release, Public Network Exposure는 **NO-GO**다. 전체 사용자 마이그레이션과 복구 백업의 영구 제거는 **UNVERIFIED**다. 이번 빌드는 로컬에서만 만들었다. [이전 독립 검증 기준](wave17-independent-validation-2026-11-26.md)
