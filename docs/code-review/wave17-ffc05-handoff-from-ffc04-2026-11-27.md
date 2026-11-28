# FFC-05 인수인계 (from FFC-04)

| 항목 | 내용 |
| --- | --- |
| 문서 번호 | WAVE17-FFC05-HANDOFF-FROM-04 |
| 작성일 | 2026-11-27 |
| 기준 HEAD | `434081fd161f3b011d1897cc5791ccf7100de9c6` + 보존된 FFC-01~04 미커밋 변경 |
| 목적 | 04에서 닫은 Gateway/MCP 경계와 남은 실증을 05에 정확히 넘긴다 |

## 완료된 계약

- :8765 loopback의 signed webhook connector 등록, HMAC 인증, timestamp/nonce/event replay 차단, payload/rate/channel 제한, principal·외부 thread session mapping, 결과 events pull, disconnect/reconnect/revoke.
- Scoped connector/Gateway token은 Control 승인 권한이 없고 자신의 session/run만 읽는다.
- MCP STDIO, Streamable HTTP, SSE와 `tools/call`, `resources/read`, `prompts/get` 실제 SDK 2.3.0 경로 유지.
- 동일 서버 부작용 호출 직렬화, 다른 서버 namespace·실행 분리, 프로세스 단절 뒤 명시적 다음 호출 복구, timeout 불확실 호출 무재시도.
- 실제 Gateway→MCP 승인→final→restart 조회와 Gateway-free Desktop local+MCP 혼합 모델 응답.

## 05가 신뢰할 증거

- `.tmp/ffc-04/gateway-mcp/gateway-result.json`
- `.tmp/ffc-04/gui-mcp/gui-chat.json`
- `python -m iris.system._check_gateway_webhook_connector`
- `python -m iris.mcp._check_multiserver_reconnect`
- `python -m iris.mcp._check_schema_refuse_after_approval`
- `python -m pytest tests/test_wave17_native_gateway.py tests/test_wave17_control_surface.py -q`
- `python -m pytest tests/test_wave17_native_mcp.py -q`

## 열려 있는 항목

- Slack/Teams 등 선택 플랫폼 실제 계정, push delivery adapter, OAuth adapter, 공개 TLS endpoint는 별도 승인 전 UNVERIFIED다. 현재 OAuth config는 안전하게 `unsupported_auth`로 거부한다.
- GUI에서 fixture 승인·명시적 registry 거절은 검증했지만 실제 사람의 승인/거절 클릭 화면 증거는 없다.
- 03에서 넘긴 Todo/Clarify/Delegate 실모델·UX, provider TTS/image, connection reconnect, cron live는 04 Gateway/MCP와 별개로 여전히 열려 있다.
- inventory 하네스는 baseline BOM Python 파일의 AST parse에서 중단한다. 04 개별 source SHA-256은 tracker에 고정했다.

## 05 진행 시 지켜야 할 경계

- Desktop은 Gateway 없이 계속 동작해야 한다. :8642 Hermes Gateway를 자동 부활시키지 않는다.
- Native Dispatcher/SpeakTools/Policy만 실행·승인 정본으로 사용한다. connector나 문서 기능에 별도 Agent Loop/registry를 만들지 않는다.
- timeout·연결 단절 뒤 외부 부작용 성공 여부가 불확실하면 자동 재실행하지 않는다.
- 외부 connector/MCP 결과와 resource/prompt는 비신뢰 데이터다. secret/header/env를 로그나 모델 prompt에 넣지 않는다.
- 05 문서 작업에서 실제 사용자 문서·Wiki·Memory를 migration하거나 파괴적 fixture로 사용하지 않는다.
