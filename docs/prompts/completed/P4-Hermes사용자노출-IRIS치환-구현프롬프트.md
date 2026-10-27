# Prompt: P4 사용자 노출 Hermes → IRIS 치환

새 Cursor 채팅에 아래 블록만 붙여 넣는다. P3 완료 후 실행.

```text
Context:
- /poteto-mode Feature (브랜드 표면만)
- 조사: live activity `[Hermes tool]`, model sync/update/gateway 문구, hermes_errors,
  skill_mcp_dialogs, setup_protocol 단계명, TTS "헤르메스", 에러 hermes doctor(에이전트 카피).
- 모듈명 hermes_* / checkout 디렉터리 hermes-agent / HERMES_* env / LICENSE Nous 고지는
  INTERNAL_OK — 이번엔 사용자·에이전트 노출 문자열만.
- NOTICE MIT 고지는 유지.

Goal:
1) 사용자 보이는 한국어/영어 UI·로그·채팅 안내에서 Hermes/헤르메스 → Iris Agent/아이리스 에이전트
   (또는 도구만 `[IRIS tool]`).
2) 에이전트 보이는 tool summary / MEMORY nudge / skills SKILL 사용자 문구 Hermes=0.
3) 업스트림 format_error 의 `hermes doctor` 가 채팅에 뜨면 Iris 쪽 explain/포장으로 가린다
   (가능하면; 설치본 turn_failure_copy 대규모 포크는 최소화).
4) 자검: rg 로 UI 핫패스 문자열 샘플 assert (settings Phase3 스타일 _check 확장 가능).

Constraints:
- 숨김 위젯 금지. 문자열 교체/삭제.
- 내부 import·파일명·프로세스 계약 대규모 rename 금지 (별 epic).
- 커밋 금지. Surgical batches OK if needed but one coherent surface.

Verify:
- rg/자검으로 [Hermes tool] 0, 주요 사용자 문구 0
- TTS normalizer Hermes 발음 항목 정리
```
