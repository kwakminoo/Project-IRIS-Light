# Iris Wiki — LLM 지식 활용 설계

> Generated-at: 2026-07-30  
> Status: 설계 (UI 그래프 개선은 동시 반영, 자동 주입·쓰기 API는 단계 구현)

## 목표

Iris Wiki를 **장기 기억 저장소**로 쓰고, 채팅·Hermes가 **검색 → 주입 → 작성/갱신 → 링크 그래프** 루프로 지식을 재사용한다.

```
[대화/작업] ──검색──▶ Wiki 노트
     ▲                    │
     │ 주입(컨텍스트)      │ 작성·갱신
     └────────── 링크 그래프(탐색) ◀──┘
```

---

## 1. 장기 기억 (Long-term memory)

| 구분 | 경로 | 역할 |
|------|------|------|
| 문서 vault | `obsidian-vault/` (`docs/`) | 제품·API·학습·아카이브 카탈로그 |
| 사용자 wiki | `~/.iris-light/iris-wiki/` (`user/`) | 프로필, 개인 메모, 세션 요약 |

**저장 단위:** 마크다운 1파일 = 1노트. frontmatter(선택)에 `tags`, `updated`, `source` 권장.

**무엇을 기억하나**

- 사용자 선호·프로필 (`profile/profile.md` — 이미 동기화)
- 프로젝트 결정·아키텍처 메모
- 대화에서 확정된 사실 (“이 PC의 IDE는 Cursor”)
- 아카이브 카탈로그 (`docs/아카이브/`)

**하지 않는 것:** 매 턴 전체 vault를 프롬프트에 넣지 않음. 토큰·비밀 유출 위험.

---

## 2. 검색 후 주입 (Retrieve → Inject)

**트리거**

1. 채팅 전송 직전 (Iris 로컬)
2. Hermes 스킬 `obsidian` / `llm-wiki` 호출 시
3. MCP `wiki.search` (추가 예정) → `wiki.open_note`

**파이프라인**

1. 쿼리 = 사용자 메시지(+ 최근 1~2턴)
2. 후보: 제목·경로·본문 상위 N자 BM25/간단 토큰 겹침 (1차), 필요 시 임베딩(2차)
3. Top-k(기본 3) 노트 발췌(노트당 ≤800자)
4. 시스템/컨텍스트 블록에만 삽입:

```text
## Iris Wiki 참고
### {title} ({rel_path})
{excerpt}
```

**가드**

- `user/` 민감 태그·키워드(주민·API KEY) 제외
- 주입 총량 상한(예: 2400자)

**현재 상태:** UI·`wiki.list_notes` / `wiki.open_note` 존재. **자동 검색 주입은 미구현 → 다음 스프린트.**

---

## 3. 작성·갱신 (Write / Update)

| 액션 | 설명 |
|------|------|
| `wiki.write_user_note` | `user/` 아래 생성·덮어쓰기 |
| `wiki.append_daily` | 일지형 append (선택) |
| 프로필 동기화 | 이미 `sync_profile_markdown` |

**규칙**

- `docs/`(repo vault) 쓰기는 개발자/명시 확인 후에만
- 에이전트 기본 쓰기 대상 = `user/`
- 갱신 시 하단에 `> updated: ISO8601` 한 줄 유지(옵션)

**채팅 UX (예정):** “이거 위키에 저장” → 제목 제안 → `user/inbox/{slug}.md`

---

## 4. 링크 그래프 (Link graph)

**구조 엣지:** 폴더 허브 ↔ 노트 (트리)

**링크 엣지:** 본문 `[[노트제목]]` / `[[경로/제목]]`

**UI**

- Wiki 워크스페이스 중앙에 지식 그래프 상시 표시 (기존 동작 유지)
- 노드 클릭 → 우측 미리보기
- 나뭇가지형 토글 버튼 실험은 되돌림

---

## 구현 로드맵

| 단계 | 내용 |
|------|------|
| A | 그래프 UI는 기존 유지 |
| B | `wiki.search` + 채팅 전송 시 Top-k 주입 |
| C | `wiki.write_user_note` MCP + “위키에 저장” |
| D | 일일/세션 요약 자동 노트 |

---

## 관련 코드

- `iris/knowledge/iris_wiki.py`
- `iris/ui/knowledge/wiki_graph_view.py`
- `iris/ui/workspaces/obsidian_workspace_page.py`
- `iris/ui/control_bindings.py` — `wiki.*`
