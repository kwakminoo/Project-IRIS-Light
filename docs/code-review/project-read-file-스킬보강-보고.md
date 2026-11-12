# project.read_file 스킬 보강 보고

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-CR-2026-11-10-read-file-skill |
| 작성일 | 2026-11-10 |
| 관련 | `_arena-read-file` Candidate A, MEMORY 12c |
| 대상 | `iris-vibe-code` SKILL, live list→read→edit |
| 목적 | MEMORY만 있던 `project.read_file`을 스킬에 맞추고 실측 검증 |

## 1. 결론

스킬에 `project.read_file` 2c 절을 넣었고, 자검이 실패→통과로 증명됐다. 설치본 스킬도 동기화했고 MEMORY nudge는 재기록됐다. 라이브 control HTTP에서 `list_files`→`read_file`→`ide.open_file`은 통과했다. `ide.edit`만 브리지에서 타임아웃했다(실측). Candidate B·truncated·진단 합성·금지 항목은 이번에 넣지 않았다.

## 2. 확인한 사실

| 항목 | 결과 | 근거 |
|---|---|---|
| 레포 SKILL에 `project.read_file` 없음 | 수정 전 | `_check_project_read_file` AssertionError |
| 수정 후 자검 | 통과 | `python -m iris.ui._check_project_read_file` |
| 설치본 동기화 | `iris-vibe-code` 재복사 | `ensure_skills_installed()` → copied `['iris-vibe-code']` |
| MEMORY nudge | updated (v33) | `ensure_memory_nudge()` |
| live list→read→open | 통과 | `.iris_light_test_tmp/project_read_list_edit_live_report.json` |
| live `ide.edit` | 타임아웃 | 동일 리포트·수동 probe. `ide.diagnostics`는 즉시 ok |
| `get_state.project_root` ≠ IDE `workspace_root` | 불일치 | companion 중 profile=`아이리스 테스트`, IDE=`컴퓨터비전` |
| `project.write_file` (open false 포함) | 타임아웃 | work_root↔IDE 정렬로 추정. 디스크 직접 시드로 우회 |

## 3. 구조

```
Hermes (스킬 iris-vibe-code / MEMORY nudge)
  → mcp__iris_control__iris_invoke
    → project.list_files
    → project.read_file  (disk UTF-8; dirty Monaco 아님)
    → ide.open_file
    → ide.edit           ← 이번 세션에서 브리지 응답 없음
      → Theia applyTextEdit
```

분기. 모델이 스킬만 보면 예전엔 write/rename/run/edit만 보여 read를 건너뛸 수 있었다. MEMORY 12c와 스킬 2c를 맞춰 그 빈 칸을 메웠다.

## 4. 코드 리뷰

| 지점 | 이번 증상에서 한 일 | 막지 못한 이유 / 비고 |
|---|---|---|
| `integrations/.../iris-vibe-code/SKILL.md` | 2c `project.read_file` 한 절 추가 | 이전엔 MEMORY만 있어 스킬 경로 모델이 옛 계약으로 갈 수 있음 |
| `iris/ui/_check_project_read_file.py` | SKILL에 `project.read_file`·Disk UTF-8·ide.save/edit 존재 assert | TDD. 수정 전 실패, 후 통과 |
| `iris/ui/_check_project_read_list_edit_live.py` | 바운드 `workspace_root`에서 list→read→open→edit | 신규. edit는 실패를 남김 |
| `hermes_memory_nudge` 12c | 이미 `project.read_file` 있음 | 스킬과 정합만 맞춤. 내용 변경 최소 |
| `project.write_file` / worktree align | 손대지 않음 | live에서 타임아웃. 시드는 디스크 직접 쓰기 |
| Theia `applyTextEdit` | 손대지 않음 | diagnostics는 되고 edit만 멈춤 |

하지 않은 일. Candidate B(`via=editor` 버퍼 읽기), oversize `truncated=true`, 진단 재검사 합성, Theia 2nd agent, Hermes terminal/browser 재활성, computer_use IDE 클릭.

## 5. 개선안

| 우선 | 항목 | 판단 |
|---|---|---|
| 다음 | `ide.edit` / `applyTextEdit` 타임아웃 원인 | list→read는 살아 있고 edit만 죽음. Candidate B와 별개 |
| 다음 | `project_root` vs IDE `workspace_root` 불일치 시 write 정렬 hang | live write가 30s+ 타임아웃. 읽기 보강과 독립 |
| 보류 | Candidate B dirty 버퍼 읽기 | nudge·스킬 honesty로 우회 중. dirty가 반복되면 재검토 |
| 보류 | 큰 파일 `truncated=true` | 지금은 oversize 하드 실패. 요청 생길 때 |
| 보류 | 진단 재검사 합성 | `ide.edit`+`ide.diagnostics` 조합으로 충분. 모델이 못 쓸 때만 |

## 6. 차용

| 이름 | 가져올 부분 | 이번에 안 가져오는 이유 |
|---|---|---|
| Candidate B DESIGN | `via=editor|disk`, bridge `readBuffer` | 루브릭에서 A가 이김. IDE 재번들·타임아웃 복잡도 |
| Cursor/VS Code FS vs TextDocument | dirty 문서 API | Theia 브리지 확장 없이는 과함 |
| 찾지 못함 | edit hang 전용 오픈소스 패치 | 로컬 브리지·QWebEngine 펌프 경로 이슈로 보임 |

## 7. 조치

1. 스킬·자검·설치본 동기화는 반영됨. Iris Agent 게이트웨이를 한 번 재시작하면 새 스킬을 확실히 읽는다.
2. 실채팅 확인은 아래 요청문으로 사용자가 한 턴 보낸다.
3. `ide.edit` 타임아웃은 별도 TDD 이슈로 잡는다. 이번 스킬 보강과 묶지 않는다.
