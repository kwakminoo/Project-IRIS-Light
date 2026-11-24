# Candidate A — `project.read_file` (disk-only UTF-8 dual of write)

| 항목 | 내용 |
|---|---|
| Arena | `_arena-read-file` / candidate-a |
| 작성일 | 2026-11-10 |
| Bias | **디스크 UTF-8** = `write_project_file` 대칭. 에디터 버퍼 우선 금지 |
| 비범위 | Theia 2차 agent · `computer_use` · Hermes terminal · IDE LSP/open |

## 한 줄

`iris_invoke`로 바인드 워크스페이스 **파일 본문**을 읽는다. 경로 = `list_files`/`write_file`과 동일. missing / escape / binary = **빈 성공 금지, 실패**.

## 1. 구조

```
Hermes loop → iris_invoke → project.read_file
  → resolve_bound_work_root → resolve_under_root
  → read_project_file (NEW, disk only) → ok{content} | err
```

쓰기와 달리 IDE 탭/`open`/stream/Companion 정렬 없음 (`list_files`처럼 디스크만).

## 2. Usage JSON

**args:** `{ "rel_path": "src/main.py" }` (`path` 별칭 OK; bound 없으면 `project_root`)

**ok result:**

```json
{
  "ok": true, "action": "project.read_file", "status": "success",
  "result": {
    "path": "C:/proj/src/main.py", "rel_path": "src/main.py",
    "bytes": 42, "encoding": "utf-8", "content": "print(1)\n"
  },
  "error": null
}
```

| 실패 | error 요지 |
|---|---|
| no bound root | `project_root required (no bound IDE workspace)` |
| `..` / escape | `invalid rel_path` / `path escapes project_root` |
| missing | FileNotFound 메시지 |
| directory | is a directory |
| binary / NUL / bad UTF-8 | `not UTF-8 text` |
| too large | `file too large (max N bytes)` |

## 3. Signatures

```python
# iris/system/project_ops.py
def read_project_file(
    project_root: str | Path, rel_path: str, *, max_bytes: int = 1_048_576
) -> dict:
    """resolve_under_root → is_file → size≤max → reject NUL → utf-8 strict
    → {path, rel_path, bytes, encoding, content}.
    Raises FileNotFoundError | IsADirectoryError | ValueError. Never fake empty ok."""

# iris/ui/control_actions/project.py
def project_read_file(window: ProjectHost, args: dict[str, Any]) -> dict[str, Any]:
    root, root_err = resolve_bound_work_root(window, args)
    if root_err or not root:
        return err_result("project.read_file", root_err or "project_root required …")
    rel = str(args.get("rel_path") or args.get("path") or "").strip()
    if not rel:
        return err_result("project.read_file", "rel_path required")
    try:
        payload = read_project_file(root, rel, max_bytes=int(args.get("max_bytes") or 1_048_576))
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, OSError, ValueError) as exc:
        return err_result("project.read_file", str(exc))
    return ok_result("project.read_file", payload)
```

Guards: size check before full read; sniff `\0`; `decode("utf-8")` strict — **no** `errors="replace"`.

## 4. Files to touch

| 파일 | 일 |
|---|---|
| `iris/system/project_ops.py` | `read_project_file` |
| `iris/ui/control_actions/project.py` | handler + `reg.register` |
| `iris/ui/control_actions/action_catalog.json` | risk=`low`, confirm=`false` |
| `iris/system/hermes_memory_nudge.py` | 한 줄 + `_NUDGE_VERSION` bump |
| `iris/ui/_check_project_read_file.py` | 실패 우선 self-check |

`DANGEROUS_ACTIONS` 미포함. IDE 번들 변경 없음.

## 5. Failing self-check first

1. escape `../x` → ok=False  
2. missing → ok=False  
3. binary `\x00…` → ok=False  
4. size > max_bytes → ok=False  
5. write then read → content round-trip  
6. catalog registered + “bound workspace” in summary  

`python -m iris.ui._check_project_read_file`

## 6. Rejected

| 대안 | 왜 버림 |
|---|---|
| Editor-buffer-first (`ide.*`/Theia doc) | write 디스크 계약과 비대칭; 탭/미저장 의존 |
| Truncate + empty-ish ok | 정직성 깨짐 — oversize는 **실패**(truncate 후속) |
| Hermes terminal cat / `computer_use` | 금지·루트 우회 |
| Theia 내부 agent read | 2차 agent loop |
| `errors="replace"` / base64 always | 바이너리 위장·개념 과다 |

## 7. MEMORY one-liner (draft)

`12c. Read body: iris_invoke → project.read_file (rel_path; list_files if unknown). Disk UTF-8; missing/escape/binary/too-large fail — never invent content without ok.`

## 조치

TDD: check 실패 → `read_project_file` → register/catalog/nudge → green → list→read→write 수동 확인.
