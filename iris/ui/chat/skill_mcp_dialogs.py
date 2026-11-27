"""Iris Skills / MCP 관리 창 — 목록·설명·추가·채팅 삽입."""

from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
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

from iris.infrastructure.iris_agent_credentials import iris_agent_home
from iris.mcp.native_manager import NativeMCPManager
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


def iris_agent_root() -> Path:
    return iris_agent_home()


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


def list_iris_agent_skills(*, limit: int = 80, include_disabled: bool = False) -> list[tuple[str, str, Path]]:
    """(name, description, skill.md path)."""
    root = iris_agent_root() / "skills"
    if not root.is_dir():
        return []
    out: list[tuple[str, str, Path]] = []
    seen: set[str] = set()
    from iris.runtime.attachment_context import _is_link
    from iris.system.execution_policy import check_path_allowed

    disabled = set() if include_disabled else _disabled_skills()
    for path in sorted(root.rglob("SKILL.md")):
        name = path.parent.name.strip()
        if (not name or name in seen or name.casefold() in disabled or _is_link(path)
                or not check_path_allowed(root, path).allowed):
            continue
        seen.add(name)
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                raw = stream.read(4096)
        except OSError:
            raw = ""
        desc = _parse_skill_description(raw)
        if len(desc) > 160:
            desc = desc[:157] + "…"
        out.append((name, desc or "(설명 없음)", path))
        if len(out) >= limit:
            break
    return out


def _disabled_skills() -> set[str]:
    import yaml

    from iris.system.iris_agent_control_sync import iris_agent_config_path

    try:
        config = yaml.safe_load(iris_agent_config_path(iris_agent_root()).read_text(encoding="utf-8")) or {}
        return {str(name).casefold() for name in (config.get("skills", {}).get("disabled", ()) or ())}
    except (OSError, AttributeError, TypeError, yaml.YAMLError):
        return set()


def list_iris_agent_mcps(*, limit: int = 40) -> list[tuple[str, str]]:
    """(name, description)."""
    labels = {
        "disabled": "비활성",
        "invalid_config": "설정 형식 오류",
        "unsupported_transport": "지원하지 않는 전송 방식",
        "unsupported_auth": "지원하지 않는 인증 방식",
    }
    return [
        (row["name"], labels.get(row["status"]) or _KNOWN_MCP_DESC.get(row["name"], row["transport"]))
        for row in NativeMCPManager(home=iris_agent_root()).catalog()[:limit]
    ]


def _sync_wiki_catalog() -> None:
    """스킬/MCP 변경 직후 Iris Wiki user 노트 갱신."""
    try:
        from iris.knowledge.iris_wiki import IrisWiki

        wiki = IrisWiki()
        root = str(iris_agent_root())
        skills = [(n, d) for n, d, _p in list_iris_agent_skills(limit=120)]
        mcps = list_iris_agent_mcps(limit=40)
        wiki.sync_skills_catalog(skills, hermes_root=root)
        wiki.sync_mcp_catalog(mcps, hermes_root=root)
    except Exception:
        pass


def add_custom_skill(name: str, description: str) -> Path:
    safe = re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-").lower()
    if not safe:
        raise ValueError("스킬 이름이 비어 있습니다")
    dest = iris_agent_root() / "skills" / "custom" / safe
    dest.mkdir(parents=True, exist_ok=True)
    md = dest / "SKILL.md"
    desc = (description or "").strip() or safe
    md.write_text(
        f"---\nname: {safe}\ndescription: >\n  {desc}\n---\n\n# {safe}\n\n{desc}\n",
        encoding="utf-8",
    )
    return md


def manage_iris_agent_skill(operation: str, name: str, text: str = "") -> dict:
    from uuid import uuid4

    from iris.runtime.attachment_context import _is_link
    from iris.system.execution_policy import check_path_allowed
    from iris.system.iris_agent_control_sync import edit_iris_agent_config

    if not re.fullmatch(r"[\w-]{1,80}", name) or operation not in {"create", "update", "enable", "disable", "remove"}:
        raise ValueError("invalid skill name or operation")
    root = iris_agent_root()
    location = root / "skills" / "custom"
    catalog = {key.casefold(): path for key, _description, path in list_iris_agent_skills(limit=500, include_disabled=True)}
    custom = location / name.lower()
    existing = catalog.get(name.casefold())
    if operation in {"enable", "disable"}:
        if existing is None:
            raise ValueError("registered skill not found")
        with edit_iris_agent_config(root) as config:
            skills = config.setdefault("skills", {})
            if not isinstance(skills, dict) or not isinstance(skills.get("disabled", []), list):
                raise ValueError("invalid disabled-skills configuration")
            disabled = [item for item in skills.get("disabled", []) if str(item).casefold() != name.casefold()]
            if operation == "disable":
                disabled.append(name.casefold())
            skills["disabled"] = disabled
    else:
        if (_is_link(location) or _is_link(custom) or _is_link(custom / "SKILL.md")
                or not check_path_allowed(root, custom, write=True).allowed):
            raise ValueError("linked custom skill paths are unavailable")
        if operation == "create" and (existing is not None or custom.exists()):
            raise ValueError("skill already exists")
        if operation != "create" and existing != custom / "SKILL.md":
            raise ValueError("operation requires a custom skill")
        if operation == "remove":
            archive = root / "archived-skills"
            if _is_link(archive) or not check_path_allowed(root, archive, write=True).allowed:
                raise ValueError("skill archive is outside the profile")
            archive.mkdir(exist_ok=True)
            custom.rename(archive / f"{name}-{uuid4().hex[:10]}")
        else:
            if not text.strip() or len(text) > 12000:
                raise ValueError("skill text must have 1 to 12,000 characters")
            add_custom_skill(name, text)
    _sync_wiki_catalog()
    return {"name": name, "operation": operation}


def add_mcp_server(name: str, command: str, args_text: str, *, model_enabled: bool = False) -> None:
    safe = re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-")
    if not safe:
        raise ValueError("MCP 이름이 비어 있습니다")
    cmd = (command or "").strip()
    if not cmd:
        raise ValueError("command가 비어 있습니다")
    NativeMCPManager(home=iris_agent_root()).register(safe, {
        "command": cmd,
        "args": args_text.split(),
        "enabled": True,
        "model_enabled": model_enabled,
        "timeout": 120,
        "connect_timeout": 60,
    })


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


def probe_mcp_ok(name: str) -> bool:
    """등록 MCP가 사용 가능·정상 연결 가능하면 True (stdio 커맨드/HTTP 사전점검)."""
    try:
        from iris.system.iris_agent_control_sync import (
            load_mcp_servers_config,
            probe_mcp_server,
        )

        cfg = load_mcp_servers_config().get(name)
        if cfg is None:
            return False
        return bool(probe_mcp_server(name, cfg).get("ok"))
    except Exception:
        return False


class _StatusDot(QLabel):
    """연결 상태 점 — ok=초록, bad=빨강."""

    def __init__(self, ok: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(8, 8)
        color = TOKENS.success if ok else TOKENS.error
        self.setStyleSheet(
            f"background-color: {color}; border-radius: 4px; border: none;"
        )
        self.setToolTip("연결 정상" if ok else "연결 비정상")


class _ItemCard(QFrame):
    use_clicked = pyqtSignal(str)

    def __init__(
        self,
        name: str,
        desc: str,
        parent: QWidget | None = None,
        *,
        status_ok: bool | None = None,
        title_color: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SkillMcpCard")
        self._name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(8)
        if status_ok is not None:
            lay.addWidget(_StatusDot(status_ok), 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(name)
        title.setObjectName("SkillMcpCardName")
        if title_color:
            # objectName QSS보다 우선 — 모델 피커 tier 색
            title.setStyleSheet(
                f"color: {title_color}; font-size: 13px; font-weight: 600; background: transparent;"
            )
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
            make_hint("Iris Agent에 연결된 스킬입니다. 「사용」으로 채팅에 넣고, 아래에서 커스텀 스킬을 추가할 수 있습니다.")
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
        skills = list_iris_agent_skills()
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
                "등록된 MCP를 「사용」으로 채팅에 넣을 수 있습니다. 모델에 허용한 서버의 도구는 호출할 때 확인합니다."
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
        self._model_enabled = QCheckBox("이 명령이 실행되는 것을 신뢰하고 모델의 도구 검색을 허용")
        add_lay.addWidget(self._model_enabled)
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
        mcps = list_iris_agent_mcps()
        if not mcps:
            empty = QLabel("등록된 MCP 서버가 없습니다.")
            empty.setObjectName("HudDialogHint")
            self._list_lay.addWidget(empty)
        else:
            for name, desc in mcps:
                card = _ItemCard(name, desc, status_ok=probe_mcp_ok(name))
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
                model_enabled=self._model_enabled.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "MCP 추가", str(exc))
            return
        self._name_edit.clear()
        self._cmd_edit.clear()
        self._args_edit.clear()
        self._model_enabled.setChecked(False)
        self._reload()
        _sync_wiki_catalog()
        QMessageBox.information(
            self,
            "MCP 추가",
            "MCP 서버 설정을 저장했습니다.",
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
    assert isinstance(list_iris_agent_skills(), list)
    assert isinstance(list_iris_agent_mcps(), list)
    assert callable(probe_mcp_ok)
    print(
        "skill_mcp_dialogs ok",
        "skills",
        len(list_iris_agent_skills()),
        "mcp",
        len(list_iris_agent_mcps()),
    )
