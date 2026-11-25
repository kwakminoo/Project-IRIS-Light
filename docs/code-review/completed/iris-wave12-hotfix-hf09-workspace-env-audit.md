# HF-09 Workspace Environment Audit

| 항목 | 내용 |
|---|---|
| 문서 번호 | W12-HF-09 |
| 작성일 | 2026-11-25 |
| 목적 | product child run 환경 일관성 확인 |

## 결론

Product 경로(`process.manage` / `project.run` / Resolver + `build_child_env`)는 기존 `_check_workspace_*` / `_check_run_env`로 PASS. Agent home/install/gateway의 `os.environ.copy`는 **별도 계약**으로 유지한다(API 키 필요). 강제 동일 scrub는 하지 않는다.

## 경로

| 표면 | 인터프리터 | 자식 env |
|---|---|---|
| process.manage start | WorkspaceEnvironmentResolver | build_child_env |
| project.run | 동일 | Runtime → build_child_env |
| IDE ▶ | iris-ide-project-python (find-only) | 터미널 셸 |
| Agent spawn | iris_agent_repo_dir / probe | os.environ.copy + scrub 변형 |

## 검증

```
.venv\Scripts\python.exe -m iris.system._check_workspace_environment
.venv\Scripts\python.exe -m iris.system._check_workspace_shell_sync
.venv\Scripts\python.exe -m iris.system._check_run_env
```

모두 ok (2026-11-25). 코드 최소 수정 없음.
