# 검증 인수인계

## 기준 환경

- 기준 HEAD `a6927b12537a507e66f8a20f447f1a5ffd7df5aa`, 초기 소스 SHA-256 `717e8c7f3185986b226e2294d4ab8930d967e2c2afb142a0a00c3979ba3fa861`.
- 최종 워킹 트리 소스 4,100개 SHA-256 `c59a27150898551ba2e787605e0f487f0777de4363338adb7c13beff2b831c1d`. 재현 명령은 `python -m scripts.validate_wave17 inventory --out .tmp/wave17-functional-closure/final-inventory`이다. [최종 인벤토리](../../.tmp/wave17-functional-closure/final-inventory/source.json)
- 제품 Python `.venv`의 3.13.7. Owned Core `0.1.2+iris.a382af23`, 활성 `iris-agent.slot-272facc0f5fd4b6f`의 Python 3.14.7 및 설치된 MCP SDK 2.x. Vendor `SOURCE_MANIFEST.json` SHA-256 `46505c9e90d5fbe9c12c49223b88e127f0a7902f2eab960b3f2da24cad0e26bc`.
- Windows x64, `gpt-oss:20b`, 기준 서버 4,096토큰, 격리 서버 12,288토큰. `IRIS_WAVE17_OLLAMA_BASE_URL`로 테스트 러너의 루프백 서버를 명시할 수 있다. [Ollama 컨텍스트 설정](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size)

## 실제 실행 증거

명령은 저장소 루트에서 실행한다. `.tmp/wave17-functional-closure` 경로에는 합성 입력과 민감정보를 제외한 실행 증거만 둔다.

| 검사 | 결과와 증거 |
|---|---|
| `python -m scripts.validate_wave17 mcp` | 기준선 0회. 격리된 실제 모델에서 검색→스키마→승인→호출→정확 응답 1회. [기준선](../../.tmp/wave17-functional-closure/baseline-mcp/mcp-results.json) · [통과](../../.tmp/wave17-functional-closure/mcp-model-context-retry/mcp-results.json) |
| `python -m scripts.validate_wave17 native`, `mixed --attempts 2` | 파일 검색→읽기 성공. 혼합 호출 추가 2회 모두 정확한 답변, 33.566초와 15.343초. 첫 번째 모델은 파일 읽기 인수를 두 번 정정했다. [Native](../../.tmp/wave17-functional-closure/native-model-routing/native-results.json) · [혼합 반복](../../.tmp/wave17-functional-closure/mixed-model-final-samples/mixed-results.json) |
| `python -m scripts.validate_wave17 gateway-restart`, `gateway-mcp` | Scoped 승인 401, Control 승인 200. 실제 MCP 응답을 재시작 뒤 세션·실행 조회와 소유자 리터럴 검색으로 복구. 호환 토큰으로 Scoped 세션을 직접 조회하면 404, 검색하면 빈 결과. [일반](../../.tmp/wave17-functional-closure/gateway-restart/gateway-result.json) · [Scoped MCP](../../.tmp/wave17-functional-closure/gateway-mcp-search-final/gateway-result.json) |
| `python -m scripts.validate_wave17 mcp-timeout` | 지연 STDIO 시간 제한 반환. [결과](../../.tmp/wave17-functional-closure/mcp-timeout/mcp-timeout.json) |
| `python -m iris.ui._check_fpr_product_gui process` | 실제 Skip·Run 클릭 3/3. Skip에서 프로세스 미기동, Run에서 ledger 소비와 stdout. [1회](../../.tmp/wave17-functional-closure/process-gui-1.log) · [2회](../../.tmp/wave17-functional-closure/process-gui-2.log) · [3회](../../.tmp/wave17-functional-closure/process-gui-3.log) |
| 첨부, OCR, Wiki | 실제 영문 0.134초, 한글 0.138초. 한글은 글자 사이 공백 편차. `iris.ui._check_pdf_page_range`, `iris.ui._check_chip_pdf_enrich`, `iris.runtime._check_ocr_fast_path` 통과. [OCR 실측](../../.tmp/wave17-functional-closure/ocr-live.json) |
| 집중 pytest | 첨부·렌더링·응답 종료·IDE·Wiki·턴 IPC·Gateway·MCP·스킬에서 58개 통과, 1개 조건부 건너뜀, 96개 하위 검사 통과. `python -m iris.ui.chat._check_transcript_no_blank_flash` 통과. [집중 회귀](../../.tmp/wave17-functional-closure/combined-focused-final.log) |
| `python -m iris.system._check_fpr13_runner --include-lifecycle` | 격리 IRIS_HOME에서 18개 통과, 7개 미실행. Owned Core 새 슬롯 설치, 실제 모델 응답, 업데이트·롤백·손상 복구와 데이터 보존. [결과](../../.tmp/wave17-functional-closure/fpr13-isolated-final/results.json) · [수명주기 로그](../../.tmp/wave17-functional-closure/fpr13-isolated-final/logs/installer_lifecycle.log) |
| Launcher 및 Setup | PyInstaller 6.22.2 Launcher, Inno Setup 6.7.3 Setup 0.1.18 빌드. 변경된 제품 소스 30개와 번들 입력 SHA-256 일치. Setup 42,591,953바이트, 미서명, SHA-256 `3b4a0d1e26c3fc406a106f0931264a1951c93cddf6d8eecb7ef3573b960a6e71`. [Launcher 로그](../../.tmp/w17-fc-build/launcher.log) · [Setup 로그](../../.tmp/w17-fc-build/setup-final.log) · [Setup 파일](../../.tmp/w17-fc-build/dist/IRIS-Setup-0.1.18.exe) |

## 재검증 대기 열

- 저장소 전체 pytest는 선택적 Aloha 통합의 의존성으로 수집 오류 5건이 발생했다. IRIS 자체 `tests/`는 Qt 네이티브 종료 `0xC0000409`로 완주하지 못했다. 분리 실행으로 스크롤·타이포그래피의 레거시 `_log` 단언 실패 21건과 WebEngine 종료 오류를 재현했다. [수집 로그](../../.tmp/wave17-functional-closure/full-pytest-final.log) · [제품 pytest](../../.tmp/wave17-functional-closure/first-party-pytest-retry.log) · [분리 실행](../../.tmp/wave17-functional-closure/chat-scroll-repro.log)
- Windows 클린 OS에서 Setup, 업데이트, 데이터 보존, 손상 슬롯 복구와 롤백 확인이 남았다. 이 PC에서는 격리 디렉터리의 Core 수명주기를 검증했다.
- 실모델 테스트는 `gpt-oss:20b`에 한정된다. 재개 시 `tests/test_chat_scroll.py`와 `tests/test_chat_typography.py`의 WebEngine 전환, Gateway 서명 Webhook·Connector 계약, 다중 모델과 문서 성능 검증을 각각 다시 실행한다. [잔여 범위](wave17-fc-tracker-2026-11-27.md)
