"""사용자 프로필 입력 창 (인적 정보만) — Iris HUD 스타일."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.database import Database
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile
from iris.ui.settings.hud_dialog import (
    configure_form,
    configure_hud_dialog,
    make_form_label,
    make_hint,
    make_scroll_body,
    make_title,
)
from iris.ui.shared.theme_tokens import TOKENS

_FIELD_ROWS: tuple[tuple[str, str, str, bool], ...] = (
    ("name", "이름", "예: 홍길동", False),
    ("occupation", "직업", "예: 소프트웨어 엔지니어", False),
    ("hobbies", "취미", "예: 게임, 독서, 등산", True),
    ("interests", "관심 분야", "예: AI, 자동화, 음악", True),
    (
        "work_tasks",
        "필요한 기능 · 주 업무/작업",
        "Iris Light에 기대하는 기능이나 자주 하는 업무를 적어 주세요.",
        True,
    ),
    ("age", "나이", "예: 28", False),
    ("gender", "성별", "예: 남성, 여성, 비공개", False),
    ("residence", "거주지", "예: 서울특별시", False),
    ("contact", "연락처", "예: 010-1234-5678", False),
    ("email", "자주 쓰는 이메일", "예: name@example.com (표시용)", False),
)


class UserProfileDialog(QDialog):
    """사용자 프로필 인적 정보 입력·저장."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._wiki = IrisWiki()
        configure_hud_dialog(
            self,
            title="사용자 프로필",
            min_w=640,
            min_h=560,
            default_w=720,
            default_h=680,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(TOKENS.spacing_xl, TOKENS.spacing_lg, TOKENS.spacing_xl, TOKENS.spacing_lg)
        root.setSpacing(TOKENS.spacing_md)
        root.addWidget(make_title("USER PROFILE"))
        root.addWidget(
            make_hint(
                "입력한 내용은 이 PC의 Iris Light DB와 Iris Wiki(~/.iris-light/iris-wiki)에만 저장됩니다. "
                "이메일 계정·IDE 설정은 설정 메뉴에서 관리합니다."
            )
        )

        scroll, content_lay = make_scroll_body()

        form_wrap = QWidget()
        form = QFormLayout(form_wrap)
        configure_form(form)
        self._fields: dict[str, QLineEdit | QTextEdit] = {}
        profile = load_user_profile(db)
        for key, label, placeholder, multiline in _FIELD_ROWS:
            if multiline:
                w: QLineEdit | QTextEdit = QTextEdit()
                w.setPlaceholderText(placeholder)
                w.setPlainText(getattr(profile, key, "") or "")
                w.setMinimumHeight(88)
                w.setMaximumHeight(160)
            else:
                w = QLineEdit()
                w.setPlaceholderText(placeholder)
                w.setText(getattr(profile, key, "") or "")
                w.setMinimumHeight(32)
            self._fields[key] = w
            form.addRow(make_form_label(label), w)
        content_lay.addWidget(form_wrap)
        content_lay.addStretch(1)

        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._existing = profile

    def _save(self) -> None:
        data: dict[str, str] = {}
        for key, widget in self._fields.items():
            if isinstance(widget, QTextEdit):
                data[key] = widget.toPlainText().strip()
            else:
                data[key] = widget.text().strip()
        # IDE/경로 필드는 설정 페이지에서만 변경 — 프로필 저장 시 유지
        data["preferred_ide"] = self._existing.preferred_ide or "cursor"
        data["ide_exe_path"] = self._existing.ide_exe_path or ""
        data["ide_cli_path"] = self._existing.ide_cli_path or ""
        data["project_root"] = self._existing.project_root or ""
        profile = UserProfile(
            **{k: v for k, v in data.items()},
            project_parents=list(self._existing.project_parents or []),
        )
        save_user_profile(self._db, profile)
        self._wiki.sync_profile_markdown(data)
        self.accept()
