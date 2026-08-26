"""Iris Wiki — LLM wiki (프로젝트 문서 vault + 로컬 사용자 wiki)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from iris.knowledge.obsidian_vault import DEFAULT_VAULT_ROOT, ObsidianVault, VaultNote

WIKI_NAME = "Iris Wiki"
DOCS_PREFIX = "docs/"
USER_PREFIX = "user/"
INBOX_DIR = "inbox"


def default_user_wiki_root() -> Path:
    base = Path.home() / ".iris-light" / "iris-wiki"
    base.mkdir(parents=True, exist_ok=True)
    return base


def slugify_note_name(title: str, *, max_len: int = 64) -> str:
    """제목 → 파일명 슬러그 (한글·영문·숫자·하이픈)."""
    s = (title or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w\-가-힣]+", "", s, flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-_") or "note"
    return s[:max_len]


@dataclass(frozen=True)
class IrisWikiNote:
    rel_path: str
    title: str
    folder: str
    source: str  # "docs" | "user"

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.folder.lower(), self.title.lower())


class IrisWiki:
    """Obsidian vault 문서 + ~/.iris-light/iris-wiki 사용자 노트."""

    def __init__(
        self,
        docs_root: Path | None = None,
        user_root: Path | None = None,
    ) -> None:
        self._docs = ObsidianVault(docs_root or DEFAULT_VAULT_ROOT)
        self.user_root = (user_root or default_user_wiki_root()).resolve()
        self.user_root.mkdir(parents=True, exist_ok=True)
        (self.user_root / "profile").mkdir(parents=True, exist_ok=True)
        (self.user_root / "schedule").mkdir(parents=True, exist_ok=True)
        (self.user_root / "integrations").mkdir(parents=True, exist_ok=True)
        (self.user_root / "learning").mkdir(parents=True, exist_ok=True)
        (self.user_root / INBOX_DIR).mkdir(parents=True, exist_ok=True)

    def list_notes(self) -> list[IrisWikiNote]:
        notes: list[IrisWikiNote] = []
        for note in self._docs.list_notes():
            folder = f"{DOCS_PREFIX}{note.folder}" if note.folder else DOCS_PREFIX.rstrip("/")
            notes.append(
                IrisWikiNote(
                    rel_path=f"{DOCS_PREFIX}{note.rel_path}",
                    title=note.title,
                    folder=folder,
                    source="docs",
                )
            )
        for path in sorted(self.user_root.rglob("*.md")):
            if path.name.startswith("."):
                continue
            rel = path.relative_to(self.user_root).as_posix()
            folder = path.parent.relative_to(self.user_root).as_posix()
            if folder == ".":
                folder = USER_PREFIX.rstrip("/")
            else:
                folder = f"{USER_PREFIX}{folder}"
            notes.append(
                IrisWikiNote(
                    rel_path=f"{USER_PREFIX}{rel}",
                    title=path.stem,
                    folder=folder,
                    source="user",
                )
            )
        notes.sort(key=lambda n: n.sort_key)
        return notes

    def read_note(self, rel_path: str) -> str:
        rel_path = (rel_path or "").strip()
        if rel_path.startswith(DOCS_PREFIX):
            return self._docs.read_note(rel_path[len(DOCS_PREFIX) :])
        if rel_path.startswith(USER_PREFIX):
            rel_path = rel_path[len(USER_PREFIX) :]
        path = (self.user_root / rel_path).resolve()
        root = self.user_root.resolve()
        if root not in path.parents and path != root:
            raise FileNotFoundError(rel_path)
        if not path.is_file():
            raise FileNotFoundError(rel_path)
        return path.read_text(encoding="utf-8")

    def write_user_note(self, rel_path: str, content: str) -> Path:
        rel_path = self._normalize_user_rel(rel_path)
        path = (self.user_root / rel_path).resolve()
        root = self.user_root.resolve()
        if root not in path.parents and path != root:
            raise ValueError("invalid user wiki path")
        if path.suffix.lower() != ".md":
            path = path.with_suffix(".md")
            rel_path = path.relative_to(root).as_posix()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_inbox_note(
        self,
        title: str,
        body: str,
        *,
        source_url: str = "",
        rel_path: str | None = None,
    ) -> tuple[Path, str]:
        """사용자 wiki에 노트 저장. 반환: (절대경로, user/ 없는 rel)."""
        title = (title or "").strip() or "untitled"
        body = (body or "").strip()
        if not body:
            raise ValueError("content required")
        if rel_path:
            rel = self._normalize_user_rel(rel_path)
        else:
            rel = f"{INBOX_DIR}/{slugify_note_name(title)}.md"
        if not rel.endswith(".md"):
            rel = f"{rel}.md"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [f"# {title}", ""]
        if source_url.strip():
            lines.append(f"- source: {source_url.strip()}")
            lines.append("")
        lines.append(body)
        lines.append("")
        lines.append(f"> updated: {stamp}")
        lines.append("")
        path = self.write_user_note(rel, "\n".join(lines))
        return path, path.relative_to(self.user_root).as_posix()

    @staticmethod
    def _normalize_user_rel(rel_path: str) -> str:
        rel = (rel_path or "").strip().lstrip("/").replace("\\", "/")
        if rel.startswith(USER_PREFIX):
            rel = rel[len(USER_PREFIX) :]
        if rel.startswith(DOCS_PREFIX) or rel == "docs" or ".." in rel.split("/"):
            raise ValueError("user wiki only — docs/ and .. paths are not allowed")
        if not rel or rel.endswith("/"):
            raise ValueError("rel_path required")
        return rel

    def sync_profile_markdown(self, profile: dict[str, str]) -> None:
        lines = [
            "# 사용자 프로필",
            "",
            "> Iris Wiki 로컬 저장 — 이 PC에만 존재합니다.",
            "",
        ]
        labels = {
            "name": "이름",
            "occupation": "직업",
            "hobbies": "취미",
            "interests": "관심 분야",
            "work_tasks": "필요한 기능 · 주 업무",
            "age": "나이",
            "gender": "성별",
            "residence": "거주지",
            "contact": "연락처",
            "email": "자주 쓰는 이메일",
        }
        for key, label in labels.items():
            val = str(profile.get(key, "") or "").strip()
            if val:
                lines.append(f"## {label}")
                lines.append("")
                lines.append(val)
                lines.append("")
        self.write_user_note("profile/profile.md", "\n".join(lines))

    def sync_email_accounts_index(self, accounts: list[dict[str, str]]) -> None:
        lines = [
            "# 이메일 계정",
            "",
            "> 비밀번호는 Iris Light DB에 암호화 저장됩니다. 이 노트에는 주소만 기록됩니다.",
            "",
        ]
        if not accounts:
            lines.append("_등록된 계정 없음_")
        else:
            for acc in accounts:
                label = acc.get("label", "")
                addr = acc.get("address", "")
                if label:
                    lines.append(f"- **{label}** — `{addr}`")
                else:
                    lines.append(f"- `{addr}`")
        self.write_user_note("profile/email-accounts.md", "\n".join(lines))

    def sync_schedule_markdown(self, events: list[dict[str, str]]) -> None:
        """사용자 wiki `schedule/index.md` — 일정 목록 동기화."""
        lines = [
            "# 일정",
            "",
            "> Iris 캘린더와 동기화됩니다. 대화로 추가·변경한 일정도 여기 반영됩니다.",
            "",
        ]
        if not events:
            lines.append("_등록된 일정 없음_")
        else:
            for ev in events:
                start = ev.get("start_at", "")
                title = ev.get("title", "")
                note = ev.get("note", "")
                place = ev.get("place", "")
                eid = ev.get("id", "")
                line = f"- `{start}` **{title}**"
                if place:
                    line += f" @ {place}"
                if note:
                    line += f" — {note}"
                if eid:
                    line += f" _(id:{eid})_"
                lines.append(line)
        lines.append("")
        self.write_user_note("schedule/index.md", "\n".join(lines))

    def sync_skills_catalog(
        self,
        skills: list[tuple[str, str]],
        *,
        hermes_root: str = "",
    ) -> None:
        """등록·사용 중인 Hermes 스킬 목록 → user/integrations/skills.md."""
        lines = [
            "# Iris Skills",
            "",
            "> Hermes `skills/` 폴더에 있는 SKILL.md 기준. Iris Composer + 메뉴와 동기화됩니다.",
            "",
        ]
        if hermes_root:
            lines.append(f"- 경로: `{hermes_root}`")
            lines.append("")
        if not skills:
            lines.append("_등록된 스킬 없음_")
        else:
            lines.append(f"**총 {len(skills)}개**")
            lines.append("")
            for name, desc in skills:
                d = (desc or "").strip() or "(설명 없음)"
                lines.append(f"- **`{name}`** — {d}")
        lines.append("")
        self.write_user_note("integrations/skills.md", "\n".join(lines))

    def sync_mcp_catalog(
        self,
        mcps: list[tuple[str, str]],
        *,
        hermes_root: str = "",
    ) -> None:
        """Hermes config.yaml mcp_servers → user/integrations/mcp.md."""
        lines = [
            "# Iris MCP Servers",
            "",
            "> Hermes `config.yaml`의 `mcp_servers` 등록분. Iris Composer + 메뉴와 동기화됩니다.",
            "",
        ]
        if hermes_root:
            lines.append(f"- 경로: `{hermes_root}`")
            lines.append("")
        if not mcps:
            lines.append("_등록된 MCP 없음_")
        else:
            lines.append(f"**총 {len(mcps)}개**")
            lines.append("")
            for name, desc in mcps:
                d = (desc or "").strip() or "(설정됨)"
                lines.append(f"- **`{name}`** — {d}")
        lines.append("")
        self.write_user_note("integrations/mcp.md", "\n".join(lines))

    def sync_learned_workflows(
        self,
        workflows: list[dict[str, str]],
    ) -> None:
        """화면 시연 학습(모니터링 학습) 결과 → user/learning/workflows.md."""
        lines = [
            "# 학습된 업무 (Learned Workflows)",
            "",
            "> 드래그 탭 학습 버튼으로 시연한 GUI 업무. 이름·요약·앱·상태가 기록됩니다.",
            "",
        ]
        if not workflows:
            lines.append("_아직 학습된 업무 없음_")
        else:
            lines.append(f"**총 {len(workflows)}개**")
            lines.append("")
            for wf in workflows:
                name = wf.get("name") or "(이름 없음)"
                summary = wf.get("summary") or ""
                apps = wf.get("primary_apps") or ""
                status = wf.get("status") or ""
                created = wf.get("created_at") or ""
                wid = wf.get("id") or ""
                tid = wf.get("trace_id") or ""
                line = f"- **{name}**"
                if status:
                    line += f" `{status}`"
                if apps:
                    line += f" · 앱: {apps}"
                if created:
                    line += f" · {created}"
                if wid:
                    line += f" _(id:{wid})_"
                lines.append(line)
                if summary:
                    lines.append(f"  - 요약: {summary}")
                if tid:
                    lines.append(f"  - trace: `{tid}`")
        lines.append("")
        lines.append("## 이름 규칙")
        lines.append("")
        lines.append(
            "1. 시맨틱 트레이스에 GitHub/메일/검색 등 패턴이 있으면 그 업무명 사용"
        )
        lines.append(
            "2. 없으면 주요 앱명 + 동작(입력/작업/스크롤 탐색/드래그 편집)"
        )
        lines.append(
            "3. 그래도 없으면 `학습된 업무 YYYY-MM-DD HHMM` 폴백"
        )
        lines.append("4. 좌표형 click 액션은 이름으로 쓰지 않음 (최대 25자)")
        lines.append("")
        self.write_user_note("learning/workflows.md", "\n".join(lines))
