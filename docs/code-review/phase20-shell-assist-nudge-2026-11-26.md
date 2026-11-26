# PHASE20 Shell Assist Nudge (R-SHELL-ASSIST soft)

| 항목 | 내용 |
|---|---|
| 문서 번호 | PHASE20-SHELL-ASSIST-2026-11-26 |
| 작성일 | 2026-11-26 |
| 관련 | R-SHELL-ASSIST · PHASE04 shell live · ACF GUI soft 이탈 |
| 대상 | Host `iris/engine` sidecar (`on_tool_complete`) |
| 목적 | 셸/터미널 도구 성공 후 다음 비서 답이 stdout을 그대로 인용하도록 soft hint |

## 1. 결론

Host sidecar만 손댔다. 성공한 `terminal` / `shell.run`(별칭 포함) 결과를 보면 `ShellAssistNudge`가 마지막 tool 메시지에 verbatim-stdout hint를 한 번만 붙인다. vendor `tool_executor` 루프·live 엔진 홈·install/SOURCE_MANIFEST는 그대로다. self-check exit 0, diagram nudge 기존 검사도 exit 0.

## 2. 확인한 사실

| # | 항목 | 값 | 근거 |
|---|---|---|---|
| 1 | shell assist check | exit 0 | `python -m iris.engine._check_shell_assist_nudge` |
| 2 | diagram nudge check | exit 0 | `python -m iris.engine.diagram_tool_nudge` |
| 3 | 배선 위치 | `on_tool_complete` | DiagramToolNudge 옆 |
| 4 | hint 재사용 | `append_hint_to_last_tool_result` | `diagram_tool_nudge.py` |
| 5 | 커밋/push | 없음 | 요청대로 |
| 6 | live engine home | 미변경 | — |

## 3. 구조

```
sidecar run_conversation
  → tool_complete_callback (on_tool_complete)
       → DiagramToolNudge.observe          (기존)
       → ShellAssistNudge.observe          ★이번 분기
            │  tool ∈ {terminal, shell.run, shell_run, shell}
            │  result ok/success + stdout/output 비어 있지 않음
            └→ append_hint_to_last_tool_result(agent, HINT)
                 → agent._session_messages 마지막 role=tool content에 HINT
  → 다음 모델 호출이 tool content(+hint)를 봄
  → ToolErrorBudget.observe                (기존)
```

이번 요청은 `on_tool_complete`에서 Diagram hint 직후 갈라진다. Speak/Control 실행 경로는 그대로다.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 요청을 막지 못한 이유 / 수정 |
|---|---|---|
| Speak `normalize_speak_invoke` | (이전) argv coerce → exit 0 | 셸 P0는 닫힘. 비서 인용은 다른 층 |
| vendor tool_executor | 미변경 | Host soft만 허용 (설계) |
| `on_tool_complete` (이전) | diagram + budget만 | 성공 shell에 hint 없음 → octokit 이탈 |
| `ShellAssistNudge` (이번) | 성공 shell 1회 fire | tool 메시지에 verbatim 지시 |
| `append_hint_to_last_tool_result` | 재사용 | 중복 append는 False |

하지 않은 일: vendor 루프 수정, system prompt 전역 변경, live `~/.iris-light` 설치, `iris_agent_install.py` / SOURCE_MANIFEST.

## 5. 개선안

1. soft hint가 실모델에서 마커 인용률을 올리는지 격리 GUI 한 턴으로 측정 (이번 단위 밖).
2. hint가 무시되면 다음 단계로 강도가 다른 계약(예: empty-assistant 가드)만 검토.

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| `DiagramToolNudge` | observe/fired/append_hint 패턴 | 조건만 shell 성공으로 바꿈 |
| vendor tool_executor patch | 결과 주입 루프 | Host-only 설계와 충돌 |
| 전역 system prompt | “always quote shell” | spam·범위 과다 |

## 7. 조치

1. `iris/engine/shell_assist_nudge.py` 추가.
2. `_sidecar_main.py` `on_tool_complete`에 배선.
3. `_check_shell_assist_nudge.py` 녹색 확인.
4. 커밋·push·live 홈 없음.
