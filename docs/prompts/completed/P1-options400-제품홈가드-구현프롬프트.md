# Prompt: P1 options 400 — 제품 홈 가드

새 Cursor 채팅에 아래 블록만 붙여 넣는다.

```text
Context:
- 저장소: Project-IRIS-Light (Windows)
- /poteto-mode Bug fix
- 증상: 채팅에 `custom rejected… hermes doctor` + HTTP 400 Unsupported parameter(s): options
- 실측: 제품 홈 `~/.iris-light/agent/hermes-agent/.../custom/__init__.py` 에
  `if ollama_num_ctx:` → `extra_body["options"]` 만 있고 iris options 가드 없음.
  레거시 `%LOCALAPPDATA%\hermes\hermes-agent\...` 에만 `# iris: ollama-options-guard` 있음.
  agent.log 실패 턴 base_url 은 NVIDIA `integrate.api.nvidia.com/v1` 이었음.
- 기존 스펙: docs/code-review/completed/Hermes채팅400-options필드-원인과-개선안.md
  코드: iris/system/hermes_ollama_guard.py, agent_runtime.apply_iris_agent_baseline_overlays
- 가드 주석: apply 는 install/update 전용이라 기동만으로는 제품 트리에 안 들어감.

Goal:
1) 제품 홈 iris_agent_repo_dir() 에 apply_ollama_options_guard 가 실제로 적용되게 한다.
2) ensure_iris_agent_runtime / gateway ensure 경로에서 가드 부재 시 1회 적용하고,
   이번에 파일이 바뀌면 gateway 1회 재시작.
3) 비-Ollama base_url 이면 sync_model_ollama_num_ctx 로 ollama_num_ctx 키 삭제 유지.
4) 로컬 Ollama(:11434) 에는 options.num_ctx 유지.
5) 자검: ollama_options_guard_present(제품 repo) True; 단위 테스트/기존 _check 통과.
6) 가능하면 제품 트리에 지금 당장 가드를 적용해 재현을 끊는다 (런타임 파일 패치 OK).

Constraints:
- Surgical. hermes_ollama_guard·agent_runtime·gateway ensure·관련 테스트만.
- 업스트림 전체 재작성 금지. custom/__init__.py options 한 분기만.
- 커밋/PR 금지 (사용자 요청 전).
- API 키 로그 금지. no-console-windows 유지.
- 가드 패턴 못 찾으면 파일 추측 덮어쓰기 금지.

Verify:
- .venv\Scripts\python.exe -c "from iris.infrastructure.agent_runtime import iris_agent_repo_dir; from iris.system.hermes_ollama_guard import ollama_options_guard_present, apply_ollama_options_guard; r=iris_agent_repo_dir(); print(r); print('before', ollama_options_guard_present(r)); print('apply', apply_ollama_options_guard(r)); print('after', ollama_options_guard_present(r))"
- 관련 unittest / _check_iris_agent_runtime_phase1 등 기존 가드 테스트
- 보고: 무엇이 깨졌는지, 원인, 고친 파일, before/after 출력

Output: 한국어 요약. diff는 최소.
```
