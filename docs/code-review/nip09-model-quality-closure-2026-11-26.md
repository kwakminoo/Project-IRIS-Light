# NIP-09 Model Quality Closure (2026-11-26)

| 항목 | 내용 |
|---|---|
| 문서 번호 | NIP-09-MQC-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | Wave 1.6 · Owned Core 0.1.2 (`iris-agent.slot-272facc0f5fd4b6f`) |
| 대상 | 로컬 모델 품질 매트릭스 (gpt-oss:20b) |
| 목적 | forced `tool_choice=required`만으로 PASS 치지 않고 시나리오 닫기 |

## 1. 결론

Overall **PARTIAL**. 일반 채팅·`tool_choice=auto` 단발 셸·컨텍스트 복구·취소는 live PASS. 멀티툴·멀티스텝·파일 쓰기·프로세스·브라우저·IDE는 PARTIAL/OPEN. 유료·미설치 모델은 approval-gated **OPEN**. `legacy_migration_approved` 미설정, hermes-agent 미삭제, 제품 selection 미변경.

증거: `.tmp/nip09-closure/STATUS.md`, `.tmp/nip09-closure/results.json`.

## 2. 시나리오 결과

| # | 시나리오 | 결과 | 근거 |
|---|---|---|---|
| 1 | General chat | PASS | HELLO live auto |
| 2 | Tool choice auto | PASS | shell.run + marker (auto) |
| 3 | Single tool call | PASS | 1× shell.run |
| 4 | Multi-tool call | PARTIAL | gpt-oss 턴당 1툴; required도 search_files 이탈 |
| 5 | Multi-step task | PARTIAL | step1 OK; StatelessTurn 무세션 메모리 |
| 6 | File R/W/edit | PARTIAL | 읽기/마커 OK, 디스크 write 불완전 |
| 7 | Shell | PASS | auto grounding |
| 7b | Shell required (ref) | PARTIAL | required-only 참고 (품질 PASS 아님) |
| 8 | Process | PARTIAL | `_check_process_manage` + live 불완전 |
| 9 | Browser | PARTIAL | 계약 PASS; live GUI OPEN |
| 10 | IDE | PARTIAL | 계약 PASS; companion live OPEN |
| 11 | Context recovery | PASS | workspace 파일 복구 |
| 12 | Error recovery | PARTIAL | fail 후 성공 경로 불완전 |
| 13 | Cancellation | PASS | cancel 계약 + live `TurnCancelled` |
| — | Paid/uninstalled | OPEN | approval-gated |
| — | List-literal coerce | PASS | `normalize_speak_invoke` |

## 3. 구조

요청 → `Engine.ensure_ready` → sidecar StatelessTurn → (tools) Speak/`shell.run` → `TurnFinished`/`TurnFailed`.

```
ChatTranscript + CancelToken
  → Engine(InternalSidecar, isolated EngineHome under .tmp/nip09-closure-homes)
    → Ollama gpt-oss:20b
    → bind_tool_handler → speak_invoke_agent_tool / stubs
    → host-watch / sidecar logs
```

갈라짐: **vague auto prompt** → Clean-EOF · `MODEL_OUTPUT_LIMIT` (툴 0회). **named terminal+args auto** → shell PASS. **required** → 단발 툴은 되나 품질 PASS로 치지 않음.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 막지 못한 이유 / 조치 |
|---|---|---|
| 격리 `config.yaml` `tool_choice` | auto/required 시드 | auto+약한 프롬프트면 EOF 루프 |
| sidecar conversation loop | 연속 4회 continuation | finish_reason 없는 reasoning → TurnFailed |
| `normalize_speak_invoke` | list-literal coerce | 계약 PASS (이미 존재) |
| `_check_owned_live_shell` | auto/required 레버 | 제품 쪽 프롬프트는 별도 강화본 존재 |
| 매트릭스 러너 `.tmp/nip09-closure/run_matrix.py` | 13시나리오 레버 | 멀티툴은 모델 한계로 PARTIAL |

하지 않은 일: live selection 쓰기, hermes 삭제, 유료 API live, GUI 브라우저/IDE companion burn.

## 5. 개선안

1. 제품 auto 경로도 “terminal + exact args” 프롬프트 규약 (required 우회 금지).
2. Clean-EOF / no-tool reasoning을 `MODEL_OUTPUT_LIMIT` 전에 조기 실패·재프롬프트.
3. 멀티툴·멀티스텝은 세션 연속 턴 하니스 + 추가 로컬 모델 매트릭스 (OPEN).

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| 기존 `_check_owned_live_*` | EngineHome 격리·approval fixture | 이미 재사용 |
| Hermes tool_choice overlay | required/auto 의미 | 제품 배선 유지, live demotion 목록 비개입 |
| 외부 eval harness | 멀티모델 스위트 | 유료/미설치 OPEN |

## 7. 조치

1. 증거·러너: `.tmp/nip09-closure/`
2. Wave 2: 여전히 NIP-12/NIP-13·멀티툴 잔여로 차단 가능
3. 커밋/푸시 없음 (요청 없음)
