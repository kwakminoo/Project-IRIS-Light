# Prompt: P3 MEMORY/스킬 sync drift

새 Cursor 채팅에 아래 블록만 붙여 넣는다. P2 완료 후 실행.

```text
Context:
- /poteto-mode Bug fix
- 바탕화면 폴더 생성 턴: tool_turns=0, 모델이 physical folders 불가라고 지어냄.
- 원인 축 (조사됨):
  - terminal/browser toolset 비활성은 의도.
  - iris-control MCP 는 deferred (tool_search).
  - 런타임 MEMORY = iris-control-nudge-v26, 레포 = v29.
  - 런타임 iris-work-start 스킬이 MCP-only 구버전, 레포는 native seed 우선.
  - sync JSON skills_ok / memory already present 인데 내용이 최신 아님.
  - create_scaffold 가 runtime MEMORY에 약함. native seed에 create_scaffold 없음.
- 코드: hermes_memory_nudge.py, hermes_iris_control_sync.py, integrations/hermes-skills/

Goal:
1) MEMORY 마커 버전이 낮으면 "already present"로 skip 하지 말고 v29(+현재)로 갱신.
2) 스킬 바이트/해시가 레포와 다르면 강제 재복사.
3) nudge/스킬에 project.create_scaffold(+ Desktop parent, open IDE) 경로를 모델이 찾게 명시.
4) 제품 홈에 지금 당장 sync를 돌려 MEMORY·skills 를 레포와 맞춘다.
5) 자검: runtime MEMORY 마커 == repo; work-start SKILL 해시 일치; create_scaffold 문자열 존재.

Constraints:
- Surgical. sync·nudge·스킬 텍스트·자검만. tool_search 엔진 개편·terminal 재활성화는 이번 범위 밖 (별 이슈면 보고만).
- 커밋 금지.

Verify:
- sync 함수 호출 후 MEMORY/skills diff 없음 (또는 updated 로그)
- 짧은 assert 스크립트 또는 기존 sync self-check
```
