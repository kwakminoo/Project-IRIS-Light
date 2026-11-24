# Phase A Design — Candidate B: Bound Probe Capsule

| 항목 | 내용 |
|---|---|
| 문서 | arena candidate-b |
| 작성일 | 2026-11-10 |
| 범위 | bound workspace content search · git status/diff · project.delete human confirm |
| 비범위 | agent-desktop · agent-browser · free-form OS shell · process kill · git commit/push |
| 형태 | **Bound Probe Capsule** — `project.*`/`workspace.*`/`ide.*`와 분리된 `bound.*` 읽기 전용 렌즈 |

## 한 줄 결론

모델이 Hermes terminal/browser 없이 bound 루트만 들여다보게 하려면, HUD용 `workspace.*`와 변이용 `project.*` 옆에 **읽기 전용 `bound.*` Capsule**을 두고, 삭제는 기존 DANGEROUS_ACTIONS 봉인으로 `confirm_required`를 강제한다.

---

## 1. Usage

### 언제 쓰는가

| 의도 | 액션 | 비고 |
|---|---|---|
| 파일 **이름** 찾기 | 기존 `project.list_files` | 경로 substring |
| 파일 **내용** 찾기 | **`bound.grep`** | 라인 단위 hit |
| 변경 요약 | **`bound.git_status`** | porcelain 파싱 |
| 패치 보기 | **`bound.git_diff`** | path 선택 가능 |
| 폴더/파일 삭제 | `project.delete` | **이제 HUD 확인 필수** |

### 계약 (모델·런타임)

1. 진입은 오직 `mcp__iris_control__iris_invoke` → `ActionRegistry`.
2. Hermes `terminal` / page-driving `browser` toolset는 계속 disabled. 이 Capsule이 그 자리를 **대체하지 않고**, bound 루트 읽기만 채운다.
3. `IrisIdeClient.get_git_status` / `get_git_diff`는 **IRIS IDE 브리지 전용**으로 남긴다. Control 경로는 IDE가 꺼져 있어도 디스크 루트에서 동작해야 하므로 **sealed git argv + `no_window_kwargs`** 를 쓴다.
4. `bound.*`는 confirm 없음 · risk=low · 전부 OFF_UI (긴 walk/subprocess가 Qt를 막지 않게).
5. `project.delete`는 risk=high + `confirm_required=True` + `DANGEROUS_ACTIONS` 멤버. `args.confirm`은 무시되고 HUD만 통과시킨다 (기존 control_surface 계약).

### 예시 iris_invoke 호출

```json
{
  "action": "bound.grep",
  "args": {
    "pattern": "confirm_required\\s*=\\s*False",
    "glob": "*.py",
    "path": "iris",
    "case_insensitive": false,
    "limit": 50
  }
}
```

```json
{
  "action": "bound.git_status",
  "args": {}
}
```

```json
{
  "action": "bound.git_diff",
  "args": {
    "path": "iris/engine/types.py",
    "staged": false,
    "max_bytes": 120000
  }
}
```

삭제(확인 게이트 후 실행):

```json
{
  "action": "project.delete",
  "args": {
    "project_root": "C:/Users/me/Desktop/Projects/doomed-app",
    "rel_path": "tmp/scratch.txt"
  }
}
```

루트 해석: `resolve_bound_work_root(window, args)` — `project_root` 생략 시 bound IDE/work root. `path`/`rel_path`는 `resolve_under_root`로 escape 차단.

---

## 2. Data shape

### 공통 봉투 (모든 `bound.*` result)

`ok_result` / `err_result` 바깥은 기존과 동일. `result`만 Capsule 봉투를 쓴다.

```python
BoundProbeEnvelope = {
    "root": str,              # resolve된 bound root
    "probe": "grep" | "git_status" | "git_diff",
    "engine": str,            # "python" | "rg" | "git"
    "truncated": bool,
    "payload": dict,          # probe별 본문
}
```

### `bound.grep` → payload

```python
{
    "pattern": str,
    "path": str,              # root-relative 검색 시작 ("" = root)
    "glob": str,              # 예: "*.py" / "" = all text-ish
    "hits": [
        {
            "rel_path": str,
            "line": int,      # 1-based
            "text": str,      # 잘린 한 줄 (max ~400 chars)
        },
        ...
    ],
    "hit_count": int,
    "files_scanned": int,
    "files_skipped_binary": int,
}
```

### `bound.git_status` → payload

```python
{
    "is_repo": bool,
    "branch": str | None,     # symbolic-ref 실패 시 None
    "entries": [
        {"path": str, "xy": str, "kind": "modified"|"added"|"deleted"|"renamed"|"untracked"|"ignored"|"other"},
        ...
    ],
    "entry_count": int,
    "raw_tail": str,          # 디버그용 짧은 porcelain 꼬리 (truncate)
}
```

`is_repo=False`면 `ok=True` + entries=[] + 메시지성 필드만 (예외로 죽이지 않음). 모델이 “git 없음”을 읽고 다음 행동을 고르게.

### `bound.git_diff` → payload

```python
{
    "is_repo": bool,
    "path": str,              # "" = whole tree
    "staged": bool,
    "diff": str,              # utf-8, max_bytes로 절단
    "byte_count": int,
    "truncated": bool,
}
```

### `project.delete` (기존 result, 정책만 변경)

기존 `delete_project_path` 결과 유지 (`deleted`, `kind`, `path` …). 변경은 등록 메타데이터뿐.

### 조직 구조 (누가 무엇을 소유)

```
Model
  └─ iris_invoke
       └─ ActionRegistry
            ├─ bound.*  ──► control_actions/bound_probe.py ──► system/bound_probe.py
            │                 (resolve_bound_work_root, ok/err)
            │                 (walk/search · sealed git · no_window_kwargs)
            ├─ project.delete ──► control_actions/project.py (confirm_required=True)
            │                      + types.DANGEROUS_ACTIONS
            └─ (unchanged) workspace.* = HUD mode switches only
```

---

## 3. Function signatures

### `iris/system/bound_probe.py` (신규 · Qt 없음)

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


_GIT_STATUS_ARGV = ("git", "status", "--porcelain=v1", "-b")
_GIT_DIFF_ARGV_HEAD = ("git", "diff", "--no-color")
_GIT_DIFF_ARGV_STAGED = ("git", "diff", "--no-color", "--cached")


def content_search_under_root(
    root: str | Path,
    *,
    pattern: str,
    path: str = "",
    glob: str = "",
    case_insensitive: bool = False,
    limit: int = 50,
    max_file_bytes: int = 1_048_576,
) -> dict[str, Any]:
    """Bound root 아래 내용 검색. 결과는 BoundProbeEnvelope.

    path는 resolve_under_root로 escape 검증.
    기본 엔진은 Python walk( list_workspace_files와 같은 skip dir ).
    PATH에 rg가 있으면 sealed rg argv + no_window_kwargs로 가속 후 동일 envelope.
    """
    raise NotImplementedError


def git_status_under_root(root: str | Path) -> dict[str, Any]:
    """sealed: git status --porcelain=v1 -b. cwd=root. no_window_kwargs."""
    raise NotImplementedError


def git_diff_under_root(
    root: str | Path,
    *,
    path: str = "",
    staged: bool = False,
    max_bytes: int = 120_000,
) -> dict[str, Any]:
    """sealed git diff. path 있으면 resolve_under_root 후 -- <rel>만 허용.
    free-form git 인자 금지. commit/add/push argv 테이블에 없음.
    """
    raise NotImplementedError


def _run_sealed_git(
    root: Path,
    argv: tuple[str, ...],
    *,
    timeout_s: float = 30.0,
) -> tuple[int, str, str]:
    """subprocess.run(argv, cwd=root, text=True, **no_window_kwargs()).
    argv[0] must be 'git'. 추가 인자 문자열 주입 금지.
    """
    raise NotImplementedError


def _parse_porcelain_v1(stdout: str) -> tuple[str | None, list[dict[str, str]]]:
    raise NotImplementedError
```

### `iris/ui/control_actions/bound_probe.py` (신규 · 등록 + 얇은 핸들러)

```python
from __future__ import annotations

from typing import Any

from iris.system.control_surface import ActionRegistry
from iris.ui.control_actions.hosts import ProjectHost  # 또는 BoundProbeHost Protocol


def bound_grep(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError  # resolve_bound_work_root → content_search_under_root → ok/err


def bound_git_status(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError


def bound_git_diff(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError


def register_bound_probe_actions(window: ProjectHost, reg: ActionRegistry) -> None:
    """bound.grep / bound.git_status / bound.git_diff 등록.
    confirm_required=False, risk='low'.
    """
    raise NotImplementedError
```

### 정책 봉인 (`project.delete`)

```python
# iris/engine/types.py — DANGEROUS_ACTIONS에 추가
DANGEROUS_ACTIONS = frozenset(
    {
        "project.write_file",
        "project.run",
        "project.rename_file",
        "project.create_scaffold",
        "project.delete",  # NEW
    }
)

# iris/ui/control_actions/project.py — register 시
reg.register(
    "project.delete",
    lambda args: project_delete(window, args),
    summary="...",  # 기존 문구 유지
    risk="high",
    confirm_required=True,  # was False / omitted
)
# register 끝의 assert_dangerous_actions_confirm(reg)가 이제 delete도 검사
```

### OFF_UI 추가 (`iris/system/control_surface.py`)

```python
_OFF_UI_ACTIONS = frozenset({
    # ...existing...
    "bound.grep",
    "bound.git_status",
    "bound.git_diff",
})
```

---

## 4. Module map

| 파일 | 변경 |
|---|---|
| **`iris/system/bound_probe.py`** | **신규** — content search · sealed git · porcelain parse |
| **`iris/ui/control_actions/bound_probe.py`** | **신규** — 핸들러 + `register_bound_probe_actions` |
| `iris/ui/control_bindings.py` | `_register_actions`에서 `register_bound_probe_actions` 호출 |
| `iris/engine/types.py` | `DANGEROUS_ACTIONS` += `project.delete` |
| `iris/ui/control_actions/project.py` | `project.delete`에 `confirm_required=True` |
| `iris/ui/control_actions/action_catalog.json` | `bound.*` 3건 추가 · `project.delete.confirm_required=true` · 카운트 갱신 |
| `iris/system/control_surface.py` | `_OFF_UI_ACTIONS`에 `bound.*` 3건 |
| `iris/system/hermes_memory_nudge.py` | terminal 대신 `bound.grep` / `bound.git_*` 안내 · delete는 confirm 필요 명시 |
| **`iris/system/_check_bound_probe.py`** | **신규** 자검 |
| `iris/system/_check_project_delete.py` | catalog/registry에서 confirm_required·DANGEROUS 멤버십 단언 추가 |
| `iris/ui/_check_control_action_split.py` | 카탈로그 건수(153→156) · confirm · OFF_UI 단언 |

### 손대지 않는 것

| 파일 | 이유 |
|---|---|
| `iris/infrastructure/iris_ide_client.py` | 브리지 git은 IDE UI용. Control과 결합하면 Companion 필수 의존이 생김 |
| `iris/ui/control_actions/workspace.py` | HUD 모드 스위치 네임스페이스. grep/git을 넣으면 의미가 붕괴 |
| `iris/system/project_ops.py` | 이미 ~1.2k줄. Capsule을 여기에 붙이면 읽기/쓰기 경계가 다시 흐려짐 |
| Hermes terminal/browser enable | 명시적 비범위 |

---

## 5. Rationale

### 채택: Bound Probe Capsule (`bound.*` + sealed git + 별도 모듈)

- **이름 공간 분리**: `workspace.*`는 이미 HUD(`open_browser` 등). `project.*`는 scaffold/write/run/delete 변이 중심. 읽기 렌즈를 둘 중 하나에 욱여넣으면 카탈로그·넛지·위험 정책이 섞인다.
- **IDE 브리지 비의존**: Control이 Companion HTTP 없이도 status/diff를 돌려야 한다. `IrisIdeClient` 재사용은 “IDE가 떠 있을 때만”이라는 숨은 제약을 만든다.
- **Sealed argv**: free-form shell을 열면 Phase A 비범위(임의 OS shell)로 즉시 미끄러진다. `git`/`rg`는 고정 튜플만.
- **Windows 콘솔**: 모든 subprocess는 `no_window_kwargs()` 필수 — Cascadia 깜빡임 금지 계약과 동일.
- **삭제 정책은 새 추상화 없이**: 이미 `assert_dangerous_actions_confirm`이 register 말미에 돈다. `project.delete`를 집합에 넣고 `confirm_required=True`만 맞추면 봉인이 완성된다.

### 기각한 대안

| 대안 | 기각 이유 |
|---|---|
| `project.grep` / `project.git_*`를 `project_ops`에 추가 | 동작은 맞지만 “변이 가방에 읽기를 더 넣기”라 Capsule 경계가 없음. candidate 평균치. |
| `IrisIdeClient.get_git_*`를 Control에서 호출 | IDE 미기동·브리지 다운 시 실패. 브리지 스키마와 porcelain 봉투가 달라 이중 유지비. |
| Hermes terminal 재활성 + 모델이 `git`/`rg` 직접 | 제품 계약 위반. 콘솔 창·임의 명령·commit까지 열린다. |
| `workspace.search` 등으로 HUD 모듈 확장 | 네임스페이스 충돌. “워크스페이스 열기”와 “내용 검색”이 같은 접두어. |
| 단일 `bound.probe` + `mode=` 인자 | 카탈로그/OFF_UI/요약 문자열이 mode에 묶여 도구 선택이 흐려짐. 확인 정책과도 안 맞음. |
| 내용 검색을 `git grep`만 | untracked·비git 폴더에서 공백. Python walk(+optional rg)가 bound 루트 일반 계약에 맞음. |
| `project.delete`만 confirm하고 DANGEROUS에 안 넣기 | boot assert가 누락을 못 잡음. 다음에 confirm이 빠지면 조용히 high-risk 무확인. |

---

## 6. Check plan

구현 후 에이전트가 직접:

```powershell
.venv\Scripts\python.exe -m iris.system._check_bound_probe
.venv\Scripts\python.exe -m iris.system._check_project_delete
.venv\Scripts\python.exe -m iris.ui._check_control_action_split
```

### `_check_bound_probe`가 단언할 것

1. temp root에 텍스트 파일 심고 `content_search_under_root`가 줄 번호 hit 반환.
2. `path`에 `../` 넣으면 ValueError / err_result (escape).
3. git 없는 폴더: `git_status_under_root` → `is_repo=False`, 예외 없음.
4. `git init`된 temp: status entries · diff 비어 있거나 파일 추가 후 감지.
5. `_run_sealed_git` 호출 경로에 `CREATE_NO_WINDOW` / `no_window_kwargs` 키 존재 (Windows).
6. 등록 후 catalog에 `bound.grep`/`bound.git_status`/`bound.git_diff` 존재, `confirm_required is False`, `runs_off_ui_thread(...) is True`.
7. argv 테이블에 `commit`/`push`/`reset`/`checkout` 문자열 없음 (소스 스캔 또는 frozenset 화이트리스트 단언).

### `_check_project_delete` 추가 단언

1. `project.delete` ∈ `DANGEROUS_ACTIONS`.
2. registry `spec("project.delete").confirm_required is True`.
3. `assert_dangerous_actions_confirm(reg)` 통과.
4. human_confirm이 False를 반환하면 invoke가 실행 없이 confirm 거절 봉투를 돌려줌 (기존 control_surface 동작).

### `_check_control_action_split`

1. `action_catalog.json` == `reg.catalog()` (드리프트 금지).
2. 이름 개수 153 → **156** (bound 3개).
3. catalog 항목 `project.delete.confirm_required === true`.

### 수동 스모크 (자검 통과 후)

Iris 재시작 → 채팅에서 내용 검색·git status 요청 → Cascadia/cmd 창이 안 뜨는지 · delete 요청 시 HUD CONFIRM이 뜨는지 확인.
