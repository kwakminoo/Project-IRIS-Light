"""Hermes Skills / MCP 관리 창 — 목록·설명·추가·채팅 삽입."""

from __future__ import annotations

import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.ui.settings.hud_dialog import (
    configure_hud_dialog,
    make_hint,
    make_scroll_body,
    make_title,
)
from iris.ui.shared.theme_tokens import TOKENS

_KNOWN_MCP_DESC = {
    "iris-control": "Iris Control Surface — 상태/액션(iris_get_state, iris_invoke)",
    "mobile-mcp": "Android 에뮬·앱 UI 조작 (@mobilenext/mobile-mcp)",
}


def hermes_root() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        p = Path(local) / "hermes"
        if p.is_dir():
            return p
    return Path.home() / ".hermes"


def _parse_skill_description(text: str) -> str:
    """SKILL.md frontmatter description 또는 첫 본문 줄."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            fm = text[3:end]
            # description: >\n  multi  or description: one line
            m = re.search(
                r"(?ms)^description:\s*>?\s*\n((?:[ \t]+.+\n?)+)",
                fm,
            )
            if m:
                lines = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
                return " ".join(lines).strip()
            m2 = re.search(r"(?m)^description:\s*(.+)$", fm)
            if m2:
                return m2.group(1).strip().strip("\"'")
            body = text[end + 3 :]
        else:
            body = text
    else:
        body = text
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            return s
        if s.startswith("#"):
            return s.lstrip("# ").strip()
    return ""


def list_hermes_skills(*, limit: int = 80) -> list[tuple[str, str, Path]]:
    """(name, description, skill.md path)."""
    root = hermes_root() / "skills"
    if not root.is_dir():
        return []
    out: list[tuple[str, str, Path]] = []
    seen: set[str] = set()
    for path in sorted(root.rglob("SKILL.md")):
        name = path.parent.name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        desc = _parse_skill_description(raw)
        if len(desc) > 160:
            desc = desc[:157] + "…"
        out.append((name, desc or "(설명 없음)", path))
        if len(out) >= limit:
            break
    return out


def list_hermes_mcps(*, limit: int = 40) -> list[tuple[str, str]]:
    """(name, description)."""
    cfg = hermes_root() / "config.yaml"
    if not cfg.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8", errors="replace")) or {}
        servers = data.get("mcp_servers") if isinstance(data, dict) else None
        if not isinstance(servers, dict):
            return []
        out: list[tuple[str, str]] = []
        for name, block in servers.items():
            key = str(name).strip()
            if not key:
                continue
            if key in _KNOWN_MCP_DESC:
                desc = _KNOWN_MCP_DESC[key]
            elif isinstance(block, dict):
                cmd = str(block.get("command") or "").strip()
                args = block.get("args") if isinstance(block.get("args"), list) else []
                arg_s = " ".join(str(a) for a in args[:4])
                if len(args) > 4:
                    arg_s += " …"
                desc = f"{cmd} {arg_s}".strip() or "(설정됨)"
            else:
                desc = "(설정됨)"
            if len(desc) > 160:
                desc = desc[:157] + "…"
            out.append((key, desc))
            if len(out) >= limit:
                break
        return out
    except Exception:
        # fallback: keys only
        from iris.ui.chat.composer_plus_menu import list_hermes_mcp_names

        return [(n, _KNOWN_MCP_DESC.get(n, "(config.yaml)")) for n in list_hermes_mcp_names(limit=limit)]


def _sync_wiki_catalog() -> None:
    """스킬/MCP 변경 직후 Iris Wiki user 노트 갱신."""
    try:
        from iris.knowledge.iris_wiki import IrisWiki

        wiki = IrisWiki()
        root = str(hermes_root())
        skills = [(n, d) for n, d, _p in list_hermes_skills(limit=120)]
        mcps = list_hermes_mcps(limit=40)
        wiki.sync_skills_catalog(skills, hermes_root=root)
        wiki.sync_mcp_catalog(mcps, hermes_root=root)
    except Exception:
        pass


def add_custom_skill(name: str, description: str) -> Path:
    safe = re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-").lower()
    if not safe:
        raise ValueError("스킬 이름이 비어 있습니다")
    dest = hermes_root() / "skills" / "custom" / safe
    dest.mkdir(parents=True, exist_ok=True)
    md = dest / "SKILL.md"
    desc = (description or "").strip() or safe
    md.write_text(
        f"---\nname: {safe}\ndescription: >\n  {desc}\n---\n\n# {safe}\n\n{desc}\n",
        encoding="utf-8",
    )
    return md


def add_mcp_server(name: str, command: str, args_text: str) -> None:
    safe = re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-")
    if not safe:
        raise ValueError("MCP 이름이 비어 있습니다")
    cmd = (command or "").strip()
    if not cmd:
        raise ValueError("command가 비어 있습니다")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML 필요") from exc
    path = hermes_root() / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        if not isinstance(data, dict):
            data = {}
    else:
        data = {}
    servers = data.get("mcp_servers")
    if not isinstance(servers, dict):
        servers = {}
    args = [a for a in args_text.split() if a]
    servers[safe] = {
        "command": cmd,
        "args": args,
        "enabled": True,
        "timeout": 120,
        "connect_timeout": 60,
    }
    data["mcp_servers"] = servers
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _card_qss() -> str:
    t = TOKENS
    return f"""
        QFrame#SkillMcpCard {{
            background-color: {t.panel_overlay};
            border: 1px solid {t.panel_border};
            border-radius: {t.radius_md}px;
        }}
        QFrame#SkillMcpCard:hover {{
            border-color: {t.accent_border};
            background-color: {t.panel_hover};
        }}
        QLabel#SkillMcpCardName {{
            color: {t.text_primary};
            font-size: 13px;
            font-weight: 600;
            background: transparent;
        }}
        QLabel#SkillMcpCardDesc {{
            color: {t.text_secondary};
            font-size: 11px;
            background: transparent;
        }}
        QPushButton#SkillMcpUseBtn {{
            background-color: {t.accent_primary};
            color: {t.text_primary};
            border: 1px solid {t.border_color};
            border-radius: {t.radius_sm}px;
            padding: 4px 10px;
            min-height: 22px;
            max-width: 64px;
        }}
        QPushButton#SkillMcpUseBtn:hover {{
            background-color: {t.accent_hover};
            border-color: {t.accent_border};
        }}
        QFrame#SkillMcpAddBox {{
            background-color: {t.panel_background};
            border: 1px solid {t.panel_border};
            border-radius: {t.radius_md}px;
        }}
    """


class _ItemCard(QFrame):
    use_clicked = pyqtSignal(str)

    def __init__(self, name: str, desc: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SkillMcpCard")
        self._name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(name)
        title.setObjectName("SkillMcpCardName")
        col.addWidget(title)
        sub = QLabel(desc)
        sub.setObjectName("SkillMcpCardDesc")
        sub.setWordWrap(True)
        col.addWidget(sub)
        lay.addLayout(col, 1)
        btn = QPushButton("사용")
        btn.setObjectName("SkillMcpUseBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.use_clicked.emit(self._name))
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)


class SkillsDialog(QDialog):
    skill_chosen = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="Skills",
            min_w=420,
            min_h=480,
            default_w=480,
            default_h=560,
        )
        self.setStyleSheet(self.styleSheet() + _card_qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(make_title("Skills"))
        root.addWidget(
            make_hint("Hermes에 연결된 스킬입니다. 「사용」으로 채팅에 넣고, 아래에서 커스텀 스킬을 추가할 수 있습니다.")
        )

        scroll, self._list_lay = make_scroll_body()
        root.addWidget(scroll, 1)

        add_box = QFrame()
        add_box.setObjectName("SkillMcpAddBox")
        add_lay = QVBoxLayout(add_box)
        add_lay.setContentsMargins(10, 10, 10, 10)
        add_lay.setSpacing(6)
        add_lay.addWidget(make_hint("스킬 추가 → skills/custom/<name>/SKILL.md"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("이름 (예: my-helper)")
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("간단한 설명")
        add_lay.addWidget(self._name_edit)
        add_lay.addWidget(self._desc_edit)
        row = QHBoxLayout()
        row.addStretch(1)
        add_btn = QPushButton("추가")
        add_btn.clicked.connect(self._on_add)
        row.addWidget(add_btn)
        add_lay.addLayout(row)
        root.addWidget(add_box)

        self._reload()

    def _reload(self) -> None:
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        skills = list_hermes_skills()
        if not skills:
            empty = QLabel("연결된 스킬이 없습니다.")
            empty.setObjectName("HudDialogHint")
            self._list_lay.addWidget(empty)
        else:
            for name, desc, _path in skills:
                card = _ItemCard(name, desc)
                card.use_clicked.connect(self._on_use)
                self._list_lay.addWidget(card)
        self._list_lay.addStretch(1)

    def _on_use(self, name: str) -> None:
        self.skill_chosen.emit(name)
        self.accept()

    def _on_add(self) -> None:
        try:
            path = add_custom_skill(self._name_edit.text(), self._desc_edit.text())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "스킬 추가", str(exc))
            return
        self._name_edit.clear()
        self._desc_edit.clear()
        self._reload()
        _sync_wiki_catalog()
        QMessageBox.information(self, "스킬 추가", f"저장됨:\n{path}")


class McpDialog(QDialog):
    mcp_chosen = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="MCP",
            min_w=420,
            min_h=480,
            default_w=480,
            default_h=560,
        )
        self.setStyleSheet(self.styleSheet() + _card_qss())
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(make_title("MCP Servers"))
        root.addWidget(
            make_hint(
                "Hermes config.yaml의 mcp_servers입니다. 「사용」으로 채팅에 넣고, "
                "추가 후 Hermes gateway 재연결을 권장합니다."
            )
        )

        scroll, self._list_lay = make_scroll_body()
        root.addWidget(scroll, 1)

        add_box = QFrame()
        add_box.setObjectName("SkillMcpAddBox")
        add_lay = QVBoxLayout(add_box)
        add_lay.setContentsMargins(10, 10, 10, 10)
        add_lay.setSpacing(6)
        add_lay.addWidget(make_hint("MCP 추가 → config.yaml mcp_servers upsert"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("이름 (예: my-mcp)")
        self._cmd_edit = QLineEdit()
        self._cmd_edit.setPlaceholderText("command (예: npx)")
        self._args_edit = QLineEdit()
        self._args_edit.setPlaceholderText("args (공백 구분, 예: -y @pkg/mcp@latest)")
        add_lay.addWidget(self._name_edit)
        add_lay.addWidget(self._cmd_edit)
        add_lay.addWidget(self._args_edit)
        row = QHBoxLayout()
        row.addStretch(1)
        add_btn = QPushButton("추가")
        add_btn.clicked.connect(self._on_add)
        row.addWidget(add_btn)
        add_lay.addLayout(row)
        root.addWidget(add_box)

        self._reload()

    def _reload(self) -> None:
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        mcps = list_hermes_mcps()
        if not mcps:
            empty = QLabel("등록된 MCP 서버가 없습니다.")
            empty.setObjectName("HudDialogHint")
            self._list_lay.addWidget(empty)
        else:
            for name, desc in mcps:
                card = _ItemCard(name, desc)
                card.use_clicked.connect(self._on_use)
                self._list_lay.addWidget(card)
        self._list_lay.addStretch(1)

    def _on_use(self, name: str) -> None:
        self.mcp_chosen.emit(name)
        self.accept()

    def _on_add(self) -> None:
        try:
            add_mcp_server(
                self._name_edit.text(),
                self._cmd_edit.text(),
                self._args_edit.text(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "MCP 추가", str(exc))
            return
        self._name_edit.clear()
        self._cmd_edit.clear()
        self._args_edit.clear()
        self._reload()
        _sync_wiki_catalog()
        QMessageBox.information(
            self,
            "MCP 추가",
            "config.yaml에 저장했습니다.\nHermes gateway 재연결을 권장합니다.",
        )


if __name__ == "__main__":
    sample = """---
name: demo
description: >
  First line of desc
  second line
---

# Demo
"""
    d = _parse_skill_description(sample)
    assert "First line" in d, d
    assert "second line" in d, d
    d2 = _parse_skill_description("---\nname: x\ndescription: one liner\n---\n\nBody\n")
    assert d2 == "one liner", d2
    assert isinstance(list_hermes_skills(), list)
    assert isinstance(list_hermes_mcps(), list)
    print(
        "skill_mcp_dialogs ok",
        "skills",
        len(list_hermes_skills()),
        "mcp",
        len(list_hermes_mcps()),
    )
