# Native Gateway 및 MCP 계약

## HTTP와 소유권

기존 Control 리스너의 `127.0.0.1:8765`와 `IRIS_NATIVE_GATEWAY_ENABLED=1`을 사용한다. `/v1/invoke`, `/v1/catalog`, `/v1/state`는 기존 Control Bearer를 사용한다.

| 경로 | 권한 | 응답 |
|---|---|---|
| GET `/v1/agent/health`, `/capabilities` | `read` | 설치·준비 상태와 허용된 기본 모델 도구 |
| POST `/v1/agent/runs` | `run` | `message`와 선택적 소유 `session_id`, 202 및 `run_id` |
| GET `/v1/agent/runs/{id}`, `/sessions/{id}` | `read` + 소유권 | 실행 상태 또는 저장된 대화. 다른 주체의 ID는 404 |
| GET `/v1/agent/sessions/search?q=...` | `read` + 소유권 | 소유 메시지의 리터럴 검색. 최근 20개까지 세션 ID, 역할과 최대 300자 스니펫 |
| GET `/v1/agent/runs/{id}/events?after=N` | `read` + 소유권 | NDJSON로 `seq` 이후 이벤트. 보존 구간 밖의 커서는 `gap` |
| POST `/v1/agent/runs/{id}/cancel` | `cancel` + 소유권 | 실행 중이면 202와 취소 요청. 종료 건은 저장된 상태 |
| POST `/v1/agent/tokens` | Control Bearer | 주체와 새 토큰 발급. `scopes`, `ttl_seconds` 선택 가능 |
| POST `/v1/agent/tokens/{id}/rotate` 또는 `/revoke` | Control Bearer | 주체를 유지하며 토큰 교체 또는 토큰 폐기 |
| GET/POST `/v1/agent/runs/{id}/approval` | Control Bearer | 실제 인수 미리보기 또는 현재 `approval_id`의 `approve`/`deny` 결정 |

SQLite에는 토큰 해시와 만료 시각만 저장한다. 기본 토큰 범위는 `read`, `run`, `cancel`이며 `mcp`는 명시적으로 부여한다. 기존 Control 토큰의 호환 주체는 `iris.local_gateway`이고, `IRIS_NATIVE_GATEWAY_ALLOW_CONTROL_TOKEN=0`으로 일반 Gateway 실행에서 해당 자격을 비활성화할 수 있다. Scoped 토큰은 자신의 실행만 조회하며 Control 액션에 사용할 수 없다.

Gateway 파일은 Desktop DB 옆의 `<stem>-gateway<suffix>`다. 제품의 대화·메시지 스키마를 그대로 쓰고, 서로 다른 주체가 소유한 대화를 Gateway 매핑으로 제한한다. 검색어는 1–200자이며 SQLite의 영문 대소문자 접기와 리터럴 비교를 사용한다. 실행 중 전원이 꺼진 레코드는 `interrupted` 이벤트를 추가하고 저장된 기존 턴에서 새 요청을 받을 수 있다. 최근 256개 이벤트를 실행별로 유지한다.

## MCP 모델 경로

일반 설정의 명시적 `model_enabled: true`는 등록된 서버의 검색·연결을 허용한다. Gateway에서 모델에 노출하려면 해당 설정에 `gateway_enabled: true`, Scoped 토큰에 `mcp`가 함께 필요하다. 실행은 단발 승인 대상이다. Gateway는 `approval_required`와 `approval_resolved`를 전달하고 90초 동안 Control 결정을 기다린다.

Host가 등록 서버 이름, 외부 도구명, 실제 JSON Schema, 설정 지문과 연결 세대를 턴에 고정한다. 모델은 공급자에 안전한 이름과 스키마만 받아 `tool_search`, `tool_describe`, `tool_call` 또는 직접 도구로 요청한다. Host는 턴, 세션, Workspace, 실행 ID, 바인딩 지문, 중복 호출을 확인한다. 실행 전 현재 설정과 같은 연결의 라이브 스키마를 비교한다.

SDK는 STDIO, Streamable HTTP, SSE를 사용한다. 일반 HTTP는 루프백에 한하며 TLS 원격 연결은 등록 URL만 사용한다. 리다이렉트와 프록시 환경 상속을 끈다. 타임아웃이나 잘린 응답에서 실행 결과가 불명확하면 `execution_uncertain`을 알린다. 외부 결과는 불신 데이터로 표시한다. 리소스 읽기와 프롬프트 조회는 현재 Host SDK API를 제공한다.

남은 범위는 서명 Webhook·Connector, 외부 호출 병렬화와 앱 리소스의 모델 경로다. [검증 인수인계](wave17-fc-validation-handoff.md)
