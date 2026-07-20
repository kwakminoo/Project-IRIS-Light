"""Obsidian vault — 프로젝트 내 마크다운 노트 탐색."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VAULT_ROOT = PROJECT_ROOT / "obsidian-vault"


@dataclass(frozen=True)
class VaultNote:
    rel_path: str
    title: str
    folder: str

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.folder.lower(), self.title.lower())


class ObsidianVault:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or DEFAULT_VAULT_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def list_notes(self) -> list[VaultNote]:
        notes: list[VaultNote] = []
        if not self.root.is_dir():
            return notes
        for path in sorted(self.root.rglob("*.md")):
            if path.name.startswith("."):
                continue
            rel = path.relative_to(self.root).as_posix()
            folder = path.parent.relative_to(self.root).as_posix()
            if folder == ".":
                folder = ""
            title = path.stem
            notes.append(VaultNote(rel_path=rel, title=title, folder=folder))
        notes.sort(key=lambda n: n.sort_key)
        return notes

    def read_note(self, rel_path: str) -> str:
        path = (self.root / rel_path).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise FileNotFoundError(rel_path)
        if not path.is_file():
            raise FileNotFoundError(rel_path)
        return path.read_text(encoding="utf-8")

    def note_path(self, rel_path: str) -> Path:
        return (self.root / rel_path).resolve()
