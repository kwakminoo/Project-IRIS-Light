"""Iris Wiki — LLM wiki (프로젝트 문서 vault + 로컬 사용자 wiki)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from iris.knowledge.obsidian_vault import DEFAULT_VAULT_ROOT, ObsidianVault, VaultNote

WIKI_NAME = "Iris Wiki"
DOCS_PREFIX = "docs/"
USER_PREFIX = "user/"


def default_user_wiki_root() -> Path:
    base = Path.home() / ".iris-light" / "iris-wiki"
    base.mkdir(parents=True, exist_ok=True)
    return base


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
        rel_path = rel_path.lstrip("/")
        path = (self.user_root / rel_path).resolve()
        root = self.user_root.resolve()
        if root not in path.parents:
            raise ValueError("invalid user wiki path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

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
