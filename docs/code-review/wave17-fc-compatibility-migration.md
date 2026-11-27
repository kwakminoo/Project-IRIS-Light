# 호출부 및 호환 이전표

| 호출 표면 | 정본과 전환 |
|---|---|
| `NativeMCPManager.discover(name, timeout, cancelled)` | 기존 호출 유지. Host 내부에서만 사용할 선택적 `expected_config` 추가. 새 `call_tool`, `read_resource`, `get_prompt`는 같은 SDK helper를 사용. |
| `engine_tool_bindings(surface)`, `Engine.bind_tool_handler(handler)` | Native 호출 계약 유지. 실제 MCP는 Host가 보내는 턴별 모델용 투영과 검증을 사용. Gateway 승인 콜백은 `Engine.bind_mcp_approval`로 전달. |
| `tool_search`, `tool_describe`, `tool_call` | 입력 필드 유지. 외부 출처는 조회 응답에서 식별. Owned Core의 unwrap을 Host 스냅샷과 일치하도록 제품 Sidecar에서 교체. |
| `NativeGateway(resolve_target)` | 선택적 `db_path`, `allow_control_token` 추가. 기존 HTTP 경로 유지. 새 `GET /v1/agent/sessions/search`는 요청 주체의 저장 메시지만 검색. |
| `edit_mcp_servers(home)` | 기존 원자적 YAML 업데이트 계약 유지. 원본 백업은 최초 한 번이며 스킬 상태 편집과 같은 구성 쓰기 경로를 공유. |
| `resolve_attachment_source(store, id)` | 선택적 `relative_path`, `workspace_root` 추가. 저장소의 권한 검증 메서드에 위임. |
| `content.extract`, `content.dump_lab_scripts` | 경로 기반 인수와 새 ID 기반 인수 공존. `relative_path`로 폴더 내 파일 접근. 실습 파일 추출 중복 정의 통합. |
| `read_pdf_pages`, `extract_from_source` | 기존 결과 본문과 페이지 상태 유지. `cancelled`, `ocr_language`와 `DocumentExtractionError(ValueError)` 추가. |
| `ChatSession`, `AttachmentWorker` | 기존 호출에 선택적 워크스페이스와 SQLite 첨부 참조 의존성 추가. 기존 SQLite에는 추가 테이블만 생성. |
| Transcript 검사 | 첨부·렌더링 검사가 실제 WebEngine DOM을 확인한다. 스트림 종료 조합은 호스트가 렌더링한 Transcript HTML을 사용한다. 스크롤·타이포그래피 회귀에는 레거시 `_log` 사용이 남아 있다. |

`iris_agent_gateway.py`, `vendor/iris-agent-core/gateway` 및 진단·복구 경로는 대체 기능 검증 완료를 기다린다. Vendor의 버전·매니페스트와 라이선스 원본 유지. [기능 마감 추적표](wave17-fc-tracker-2026-11-27.md)
