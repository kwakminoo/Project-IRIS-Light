# Phase A Design — Bound Inspect Capsule (BIC)

| 항목 | 내용 |
|---|---|
| 문서 | arena candidate-A |
| 작성일 | 2026-11-10 |
| 범위 | 바인드 워크스페이스 content search · git status/diff · `project.delete` 인간 확인 |
| 비범위 | agent-desktop · agent-browser · 임의 OS shell · process kill · git commit/push |

## 한 줄 결론

읽기 전용 검사(검색·git)는 **새 캡슐 모듈 하나**가 독점하고, 삭제 확인은 **정책 집합(DANGEROUS_ACTIONS) 한 줄**로 맞춘다. IDE 브리지 git·Hermes 터미널은 쓰지 않는다.

---

## 1. Usage

### 모델이 쓰는 길

```
모델 → MCP iris_invoke → ActionRegistry → (inspect | mutate)
                                         │
                    ┌────────────────────┴────────────────────┐
                    │ BoundInspectCapsule (read-only)         │
                    │  project.search_content                 │
                    │  project.git_status                     │
                    │  project.git_diff                       │
                    │  — subprocess + no_window_kwargs only — │
                    └─────────────────────────────────────────┘
                    │ mutate (기존) + policy latch
                    │  project.delete  → confirm_required + DANGEROUS_ACTIONS
```

- Hermes terminal/browser toolset는 계속 disabled.
- 검색·git는 **바인드 루트 밖 경로 거부** (`resolve_bound_work_root` → `resolve_under_root`).
- `IrisIdeClient.get_git_*`는 IRIS IDE 브리지 전용으로 남기고, 컨트롤 액션은 **디스크의 `.git` + `git` CLI**만 본다.

### 호출 예시 (iris_invoke 본문)

**1) 바인드 워크스페이스에서 문자열 검색**

```json
{
  "action": "project.search_content",
  "args": {
    "pattern": "confirm_required",
    "glob": "*.py",
    "path": "iris/ui",
    "case_insensitive": true,
    "max_matches": 80
  }
}
```

**2) git status (커밋 없음)**

```json
{
  "action": "project.git_status",
  "args": {}
}
```

**3) 파일 단위 diff (커밋 없음)**

```json
{
  "action": "project.git_diff",
  "args": {
    "path": "iris/engine/types.py",
    "staged": false
  }
}
```

**4) 삭제 — 인간 확인 필수 (Phase A 정책)**

```json
{
  "action": "project.delete",
  "args": {
    "project_root": "C:/Users/me/Projects/demo-app",
    "rel_path": "tmp/scratch.txt"
  }
}
```

확인 UI가 수락하기 전에는 레지스트리가 실행하지 않는다 (`confirm_required=True`).

### README 한 단락

Phase A는 “에이전트가 터미널을 연다”가 아니라 **바인드된 프로젝트에 대한 세 가지 검사 티켓 + 삭제 확인 래치**다. 검색은 파일 내용(grep/rg), git은 porcelain 조회만. 쓰기는 기존 `project.write_file` / `rename` / `run` / `create_scaffold`와 같이 확인 경로를 탄다. `project.delete`를 그 집합에 넣는다.

---

## 2. Data shape

### 공통 래퍼 (기존 계약 유지)

모든 액션 응답:

```python
# ok
{"ok": True, "action": str, "status": "success", "result": {...}, "error": None}
# err
{"ok": False, "action": str, "status": "failed"|"timeout"|"invalid", "result": {...}, "error": str}
```

### InspectReport (캡슐이 항상 채우는 골격)

읽기 세 액션의 `result`는 같은 뼈대를 공유하고, `kind`로 갈라진다.

```python
InspectReport = {
    "kind": "search_content" | "git_status" | "git_diff",
    "root": str,                 # resolve된 바인드 절대경로
    "tool": str,                 # "rg" | "python-grep" | "git"
    "truncated": bool,
    "elapsed_ms": int,
    "payload": dict,             # kind별 본문
}
```

### kind별 payload

**search_content**

```python
{
    "pattern": str,
    "glob": str,                 # "" = 전체
    "path": str,                 # 루트 상대 스캔 시작점
    "matches": [
        {"path": str, "line": int, "text": str}  # text ≤ 240 chars
    ],
    "match_count": int,
    "files_with_matches": int,
    "scanned_files": int,
}
```

**git_status**

```python
{
    "is_repo": bool,
    "branch": str | None,
    "upstream": str | None,
    "ahead": int | None,
    "behind": int | None,
    "porcelain": [
        {"xy": str, "path": str, "orig_path": str | None}  # rename 시
    ],
    "clean": bool,
    "raw_tail": str,             # 디버그용 짧은 원문 ≤ 2k (모델 기본 소비는 porcelain)
}
```

**git_diff**

```python
{
    "is_repo": bool,
    "path": str,                 # "" = 워크트리 전체 (캡 적용)
    "staged": bool,
    "patch": str,                # ≤ max_bytes (기본 120_000)
    "truncated": bool,
    "stat": str,                 # `git diff --stat` 요약 한 블록
}
```

### 삭제 (기존 + 정책만 변경)

`project.delete`의 result shape는 현행 `delete_project_path` 출력을 유지한다. Phase A에서 바꾸는 것은 **실행 전 confirm**뿐.

### 정리 구조 (모듈 관점)

```
bound_inspect.py          # InspectTicket in → InspectReport out (순수 I/O)
control_actions/project.py  # window+args → resolve root → capsule → ok/err_result
engine/types.py             # DANGEROUS_ACTIONS policy set
action_catalog.json         # 카탈로그 미러
```

---

## 3. Function signatures

```python
# iris/system/bound_inspect.py
from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict


class SearchMatch(TypedDict):
    path: str
    line: int
    text: str


class InspectReport(TypedDict):
    kind: str
    root: str
    tool: str
    truncated: bool
    elapsed_ms: int
    payload: dict[str, Any]


def search_content(
    root: str | Path,
    *,
    pattern: str,
    path: str = "",
    glob: str = "",
    case_insensitive: bool = True,
    max_matches: int = 80,
    timeout_sec: float = 20.0,
) -> InspectReport:
    """바인드 루트 아래 내용 검색. path는 resolve_under_root로만 연다.

    우선순위: PATH의 rg → 없으면 Python 라인 스캔(list_workspace_files와 동일 skip dirs).
    Windows: 모든 콘솔 자식은 no_window_kwargs().
    """
    raise NotImplementedError


def git_status(
    root: str | Path,
    *,
    timeout_sec: float = 15.0,
) -> InspectReport:
    """`git status --porcelain=v1 -b`만. commit/add/push 없음."""
    raise NotImplementedError


def git_diff(
    root: str | Path,
    *,
    path: str = "",
    staged: bool = False,
    max_bytes: int = 120_000,
    timeout_sec: float = 20.0,
) -> InspectReport:
    """`git diff` / `git diff --cached`. path는 루트 상대만."""
    raise NotImplementedError


def _run_hidden(argv: list[str], *, cwd: Path, timeout_sec: float) -> subprocess.CompletedProcess[str]:
    """CREATE_NO_WINDOW 강제. shell=True 금지. 임의 argv 외부 노출 금지(모듈 private)."""
    raise NotImplementedError


def _ensure_under_root(root: Path, rel: str) -> Path:
    """resolve_under_root 위임. 탈출 시 ValueError."""
    raise NotImplementedError
```

```python
# iris/ui/control_actions/project.py  (핸들러 스케치)

def project_search_content(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    root, root_err = resolve_bound_work_root(window, args)
    if root_err or not root:
        return err_result("project.search_content", root_err or "bound workspace required")
    try:
        report = search_content(
            root,
            pattern=str(args.get("pattern") or ""),
            path=str(args.get("path") or ""),
            glob=str(args.get("glob") or ""),
            case_insensitive=bool(args.get("case_insensitive", True)),
            max_matches=int(args.get("max_matches") or 80),
        )
    except (ValueError, NotADirectoryError, OSError, TimeoutError) as exc:
        return err_result("project.search_content", str(exc))
    return ok_result("project.search_content", report)


def project_git_status(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    root, root_err = resolve_bound_work_root(window, args)
    if root_err or not root:
        return err_result("project.git_status", root_err or "bound workspace required")
    try:
        report = git_status(root)
    except (ValueError, OSError, TimeoutError) as exc:
        return err_result("project.git_status", str(exc))
    return ok_result("project.git_status", report)


def project_git_diff(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    root, root_err = resolve_bound_work_root(window, args)
    if root_err or not root:
        return err_result("project.git_diff", root_err or "bound workspace required")
    try:
        report = git_diff(
            root,
            path=str(args.get("path") or args.get("rel_path") or ""),
            staged=bool(args.get("staged", False)),
            max_bytes=int(args.get("max_bytes") or 120_000),
        )
    except (ValueError, OSError, TimeoutError) as exc:
        return err_result("project.git_diff", str(exc))
    return ok_result("project.git_diff", report)
```

```python
# iris/engine/types.py — 정책 래치

DANGEROUS_ACTIONS = frozenset(
    {
        "project.write_file",
        "project.run",
        "project.rename_file",
        "project.create_scaffold",
        "project.delete",  # Phase A
    }
)
```

```python
# register_project_actions 내부

reg.register(
    "project.search_content",
    lambda args: project_search_content(window, args),
    summary=(
        "Search file contents under the bound IDE workspace (rg/grep). "
        "Required: pattern. Optional: path, glob, case_insensitive, max_matches. "
        "Prefer this over shell grep."
    ),
    risk="low",
)

reg.register(
    "project.git_status",
    lambda args: project_git_status(window, args),
    summary="Read-only git status (porcelain) for the bound workspace. No commit.",
    risk="low",
)

reg.register(
    "project.git_diff",
    lambda args: project_git_diff(window, args),
    summary=(
        "Read-only git diff for the bound workspace. "
        "Optional: path, staged. No commit/add/push."
    ),
    risk="low",
)

reg.register(
    "project.delete",
    lambda args: project_delete(window, args),
    summary=...,  # 기존 summary 유지
    risk="high",
    confirm_required=True,  # Phase A
)
# 끝에서 assert_dangerous_actions_confirm(reg) 유지
```

OFF_UI: 세 inspect 액션은 `project.list_files` / `project.delete`와 같이 **UI 스레드 밖**에서 돈다 (`runs_off_ui_thread` 등록 — 기존 스플릿 규칙에 맞춤).

---

## 4. Module map

| 파일 | 변경 |
|---|---|
| `iris/system/bound_inspect.py` | **신규**. 검색·git CLI·숨김 서브프로세스 독점. |
| `iris/system/_check_bound_inspect.py` | **신규**. 템프 트리에서 검색/git/경로탈출/콘솔 플래그 자검. |
| `iris/ui/control_actions/project.py` | 핸들러 3개 + `register` 3개 + `project.delete`에 `confirm_required=True`. |
| `iris/engine/types.py` | `DANGEROUS_ACTIONS`에 `project.delete` 추가. |
| `iris/ui/control_actions/action_catalog.json` | 3 액션 추가; `project.delete.confirm_required=true`로 동기화. |
| `iris/system/_check_project_delete.py` | 레지스트리에서 `confirm_required`·DANGEROUS 멤버십 assert 보강. |
| `iris/ui/_check_control_action_split.py` | 카탈로그 개수·이름·`runs_off_ui_thread`·confirm 드리프트 검사 갱신. |
| `iris/system/project_ops.py` | **손대지 않음** (list/delete/write 유지; inspect I/O를 여기 넣지 않음). |
| `iris/infrastructure/iris_ide_client.py` | **손대지 않음** (브리지 git 유지, 컨트롤 평면 비사용). |

의도적 분리: mutate 대형 모듈(`project_ops`)에 console-git/rg를 섞지 않아, Phase A 이후에도 “읽기 캡슐 / 쓰기 연산” 경계가 남는다.

---

## 5. Rationale

### 채택: Bound Inspect Capsule

- **한 문(門)**: 콘솔 도구(`rg`, `git`) 호출이 한 파일에만 있다 → `no_window_kwargs` 누락 회귀를 한 자검으로 막는다.
- **통일 리포트**: 모델·로그·테스트가 `kind`만 보면 된다.
- **브리지 비의존**: Companion/IRIS IDE가 꺼져 있어도 바인드 루트만 있으면 status/diff/search가 된다.

### 기각한 대안

| 대안 | 기각 이유 |
|---|---|
| `IrisIdeClient.get_git_status/diff`를 컨트롤 액션에 연결 | 브리지·토큰·IDE 기동에 묶임. 사실상 “IDE가 켜져 있을 때만 git”. Phase A 목표(바인드 워크스페이스 검사)와 어긋남. |
| `project_ops`에 함수 추가 | 이미 삭제·실행·스캐폴드가 섞인 거대 모듈. 읽기 콘솔 I/O를 넣으면 위험 경계가 흐려짐. |
| Hermes/터미널 toolset 재활성으로 grep·git | 비범위(임의 shell)로 즉시 확장됨. 계약상 disabled 유지. |
| 단일 `project.inspect` 액션 + `mode=` | 카탈로그·confirm·위험도가 mode에 숨겨져 MCP 카탈로그가 모호해짐. 이름 세 개로 고정. |
| `project.list_files` 확장으로 content search | list는 경로 부분일치. 내용 검색과 계약을 합치면 인자·truncation·성능 의미가 붕괴. |
| Python-only grep, rg 무시 | 대형 트리에서 느림. rg가 있으면 쓰고, 없을 때만 fallback. |
| delete에 confirm만 넣고 DANGEROUS_ACTIONS 생략 | `assert_dangerous_actions_confirm` 계약과 catalog 드리프트. 둘 다 필수. |

### 삭제를 캡슐에 넣지 않은 이유

삭제는 이미 `delete_project_path` / `dangerous_delete_reason` / OFF_UI / Companion unlock 경로가 있다. Phase A 요구는 **확인 래치**이지 삭제 재구현이 아니다. 정책 집합만 고친다.

---

## 6. Check plan

구현 후 에이전트가 돌릴 자검 (순서 고정):

```powershell
# 1) 캡슐 단위 — 검색·git·경로탈출·no_window
.venv\Scripts\python.exe -m iris.system._check_bound_inspect

# 2) 삭제 정책 — confirm_required + DANGEROUS_ACTIONS + 기존 안전 삭제
.venv\Scripts\python.exe -m iris.system._check_project_delete

# 3) 카탈로그 동기화·OFF_UI·이름 집합
.venv\Scripts\python.exe -m iris.ui._check_control_action_split
```

### `_check_bound_inspect`가 통과해야 할 것

1. 임시 git 레포에서 `git_status` → `is_repo=True`, dirty 파일 porcelain에 등장.
2. 파일 수정 후 `git_diff` → patch에 마커 문자열, `max_bytes`로 truncated 가능.
3. 파일에 심은 토큰으로 `search_content` → match 1건 이상; `path=../` 탈출 → 오류.
4. `_run_hidden` 호출 kwargs에 Windows면 `CREATE_NO_WINDOW` 계열 포함 (또는 `no_window_kwargs()` 병합 검증).
5. `git commit` / `git push` argv가 모듈 소스에 없음 (정적 금지 목록).

### `_check_project_delete` 보강

- 등록 후 `reg.spec("project.delete").confirm_required is True`
- `"project.delete" in DANGEROUS_ACTIONS`
- 기존 home/iris-repo refuse·OFF_UI assert 유지

### `_check_control_action_split`

- `action_catalog.json` == `reg.catalog()`
- 새 이름 3개 존재, `project.delete.confirm_required == true`
- `runs_off_ui_thread`가 세 inspect + delete에 대해 True

완료 기준: 위 세 모듈이 모두 exit 0. Iris GUI 수동 확인은 선택(바인드 후 검색/status 한 번씩).
)
