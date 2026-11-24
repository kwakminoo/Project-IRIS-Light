# Phase A synthesis

| 항목 | 내용 |
|---|---|
| Base | candidate-a (Bound Inspect Capsule, `project.*` 액션 이름) |
| Graft from B | sealed git argv, soft `is_repo=False`, `hermes_memory_nudge`, OFF_UI 명시 |
| Rejected | `bound.*` 네임스페이스 (모델이 이미 `project.list_files`를 씀) |
| Out of scope | agent-desktop, agent-browser, shell, process kill, git commit |

## Chosen actions

- `project.search` (A의 search_content를 짧은 이름으로)
- `project.git_status`
- `project.git_diff`
- `project.delete` → `confirm_required=True` + `DANGEROUS_ACTIONS`

## Module map

- `iris/system/bound_inspect.py` (new)
- `iris/system/_check_bound_inspect.py` (new)
- `iris/ui/control_actions/project.py` (handlers + register)
- `iris/engine/types.py` (DANGEROUS_ACTIONS)
- `iris/ui/control_actions/action_catalog.json`
- `iris/system/_check_project_delete.py` (confirm asserts)
- `iris/system/control_surface.py` (OFF_UI if needed)
- `iris/system/hermes_memory_nudge.py` (search/git/delete confirm)

## Cross-judge

Parent picked after reading both designs end to end. Convergence was high on capsule + disk git + delete latch. Namespace was the only structural fork. Chose `project.*` for discoverability next to `project.list_files`.
