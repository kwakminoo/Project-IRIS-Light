# Candidate B — `project.read_file` (editor-first dual source)

Seat: arena runner B · Design sketch only · No production code

## 1. 결론

공개 액션은 하나: `project.read_file`. 바운드 워크스페이스 `rel_path`를 읽을 때 **열린 Monaco 탭과 경로가 같으면 브리지로 버퍼(`getValue`)를 우선**, 없으면 **디스크 UTF-8**. 결과는 항상 `via=editor|disk`로 출처를 밝힌다. Companion 에이전트 루프·카탈로그·nudge·self-check 파이프라인은 그대로; Theia 2nd brain / `computer_use` 금지.

## 2. Why not disk-only

`ide.edit` / `ide.save`는 이미 `via=editor`만 진실로 친다. 디스크만 읽으면 dirty 탭과 어긋난 본문으로 `write_file`/`ide.edit`를 이어 붙여 **조용한 덮어쓰기**가 난다. 공개 이름을 둘로 쪼개지 않고(`ide.read` + `project.read_disk`) **한 액션 + honesty `via`**가 vibe 루프와 맞다.

## 3. Usage (iris_invoke)

```json
{
  "action": "project.read_file",
  "args": {
    "rel_path": "src/app.py",
    "max_bytes": 200000
  }
}
```

성공 예:

```json
{
  "ok": true,
  "action": "project.read_file",
  "data": {
    "rel_path": "src/app.py",
    "content": "…",
    "via": "editor",
    "dirty": true,
    "bytes": 1234,
    "truncated": false,
    "encoding": "utf-8"
  }
}
```

- `via=editor`: 브리지가 해당 경로 탭(우선 active, 아니면 open editors 중 path match)에서 버퍼 반환. `dirty`는 문서 dirty 플래그.
- `via=disk`: 탭 없음 / 브리지 실패·타임아웃 → `resolve_under_root` 후 디스크 읽기. `dirty` 생략 또는 false.
- `truncated=true`: `max_bytes`(기본 ~200KiB) 초과 시 앞부분만; ok 유지하되 모델은 전문이라고 말하지 않음.
- 실패: 루트 없음, `..` escape, missing path(에디터·디스크 둘 다 없음), binary/decode 실패 → `err_result`, 빈 문자열 ok 금지.

## 4. Signatures (스케치)

```python
# iris/system/project_ops.py
def read_project_file(root: Path, rel: str, *, max_bytes: int = 200_000) -> dict: ...
# → rel_path, content, bytes, truncated, encoding; raises ValueError/OSError/UnicodeDecodeError

# iris/infrastructure/iris_ide_client.py
def read_buffer(self, path: str) -> dict: ...
# → {content, path, dirty, via:"editor"} | {noEditor: true}

# iris/ui/control_actions/project.py
def project_read_file(window: ProjectHost, args: dict) -> dict: ...
# resolve_bound_work_root → resolve_under_root →
#   try bridge read_buffer(norm_rel) if iris_ide session
#   else / on noEditor → read_project_file
```

브리지 쪽: `iris-ide-bridge-ops.ts`에 `readBuffer` (기존 `widgetFor` + `modelOf().getValue()` + `document.dirty`). 새 Theia 에이전트 없음.

## 5. 구조 (요청 경로)

```
iris_invoke(project.read_file)
  → ControlSurface registry (project.py register)
  → resolve_bound_work_root / resolve_under_root   # list_files·write_file과 동일
  → [iris_ide] IrisIdeClient.read_buffer ──via=editor──┐
  → else read_project_file(disk) ────────via=disk──────┴→ ok_result + honesty
  → hermes_memory_nudge / iris-vibe-code / action_catalog.json / MCP iris_invoke 문구
```

## 6. Files to touch (구현 시)

| 파일 | 역할 |
|---|---|
| `iris/system/project_ops.py` | `read_project_file` (디스크·truncate·binary 거부) |
| `iris/ui/control_actions/project.py` | `project_read_file` + `reg.register` |
| `iris/ui/control_actions/action_catalog.json` | 카탈로그 행 |
| `iris/infrastructure/iris_ide_client.py` | `read_buffer` RPC |
| `integrations/iris-ide/src/browser/iris-ide-bridge-ops.ts` (+ bridge server/standalone) | `readBuffer` |
| `iris/system/hermes_memory_nudge.py`, `integrations/hermes-skills/iris-control/iris-vibe-code/SKILL.md` | read→edit 계약, `via` 정직 |
| `iris/mcp/iris_control_stdio.py` | iris_invoke 설명 한 줄 |
| `iris/ui/_check_project_read_file.py` (신규) 또는 `project_ops` self-check | 실패 케이스 먼저 |

IDE 번들 마커가 늘면 세션 끝 `sync_workspace_build` (규칙). Companion 루프/computer_use 손대지 않음.

## 7. Failing tests first

1. `rel_path=../outside` → err (escape), content 없음.
2. 바운드 루트 없음 → err (`project_root required…`).
3. 디스크·탭 모두 없음 → err (missing), `ok`+빈 content 금지.
4. UTF-16/널 바이너리 → err (binary/decode), fake utf-8 금지.
5. `max_bytes`보다 큰 파일 → `truncated=true`, `len(content)≤max_bytes`.
6. dirty Monaco ≠ 디스크: path=active editor → `via=editor`, content=버퍼(디스크와 달라도 ok).
7. 같은 path지만 탭 닫힘 → `via=disk`, 디스크 바이트.
8. 브리지 타임아웃 → disk fallback + `via=disk` (에러로 위장한 빈 ok 금지).
9. 카탈로그/`get_catalog`에 `project.read_file` 존재; nudge에 “read then edit, trust via” 한 줄.

## 8. Rejected alternatives

| 대안 | 기각 이유 |
|---|---|
| 디스크 전용 `project.read_file` | dirty 탭과 불일치; edit/save honesty와 비대칭 |
| 별도 `ide.read_buffer` + disk 액션 | 모델이 둘 중 고르다 틀림; 공개 이름 하나 유지가 vibe 계약 |
| 항상 에디터만 (디스크 실패) | 닫힌 파일·비 IDE 세션에서 read→write 루프 붕괴 |
| 양쪽 content를 항상 dual payload | 토큰 낭비; `via` 하나로 충분 |
| Theia AI / Hermes `computer_use`로 화면 읽기 | 금지; Control Surface가 정본 |
| 읽기 성공을 가장한 빈 문자열 | honesty 위반 (루브릭 3) |

## 9. 조치 (구현 순서 스케치)

1. Self-check에 위 실패 케이스 assert만 추가(아직 액션 없음 → red).
2. `read_project_file` + bridge `readBuffer` + `project_read_file` 배선.
3. 카탈로그·nudge·vibe skill·MCP blurb.
4. Self-check green → IDE 번들 sync(브리지 변경 시).
