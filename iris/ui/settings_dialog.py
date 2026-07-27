"""Iris Light 설정 — Ollama / Hermes / 이메일 / IDE."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from iris.config.settings import Settings
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.database import Database
from iris.storage.email_accounts import (
    add_email_account,
    load_email_accounts,
    remove_email_account,
)
from iris.storage.user_profile import UserProfile, load_user_profile, save_user_profile
from iris.system.ide_launcher import get_ide_spec, ide_catalog, is_ide_installed
from iris.ui.email_workers import EmailVerifyWorker
from iris.ui.ide_icons import ide_icon_for, show_ide_not_installed_dialog


@dataclass(frozen=True)
class LightSettingsSelection:
    ollama_base_url: str
    ollama_model: str
    hermes_enabled: bool
    hermes_command: str
    hermes_base_url: str
    hermes_api_key: str


class SettingsDialog(QDialog):
    """연결 설정 + 이메일 계정 + IDE Companion."""

    def __init__(self, settings: Settings, db: Database | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iris Light 설정")
        self.setMinimumWidth(560)
        self.setMinimumHeight(640)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self._settings = settings
        self._db = db
        self._wiki = IrisWiki()
        self._result: LightSettingsSelection | None = None
        self._accounts = load_email_accounts(db) if db is not None else []
        self._verify_worker: EmailVerifyWorker | None = None
        profile = load_user_profile(db) if db is not None else UserProfile()
        self._preferred_ide = (profile.preferred_ide or "cursor").strip().lower() or "cursor"
        self._ide_exe_path = profile.ide_exe_path or ""
        self._ide_cli_path = profile.ide_cli_path or ""
        self._project_root = profile.project_root or ""
        self._project_parents = list(profile.project_parents or [])
        self._parents_customized = bool(self._project_parents)
        self._profile_base = profile

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        self.setStyleSheet(
            """
            QDialog, QWidget {
                font-family: "Noto Sans KR", "Segoe UI Variable", "Segoe UI", "Malgun Gothic";
                font-size: 13px;
            }
            QLineEdit, QListWidget {
                background-color: #1a1c24;
                color: #ffffff;
                border: 1px solid #3f3f5f;
                border-radius: 4px;
                padding: 6px;
            }
            QToolButton {
                background-color: #1a1c24;
                color: #e8ecff;
                border: 1px solid #3f3f5f;
                border-radius: 8px;
                padding: 6px 4px;
            }
            QToolButton:checked {
                border: 2px solid #5a8fff;
                background-color: #243044;
            }
            QToolButton:hover {
                border-color: #5a8fff;
            }
            """
        )

        title = QLabel("설정")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setSpacing(16)

        conn_hint = QLabel(
            "Ollama 모델 목록과 Hermes Agent API(gateway) 연결을 설정합니다. "
            "Hermes 사용 시 채팅은 Hermes API로 전달되며, 선택한 모델이 Hermes에도 동기화됩니다."
        )
        conn_hint.setWordWrap(True)
        content_lay.addWidget(conn_hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._ollama_url = QLineEdit(settings.ollama_base_url)
        self._ollama_model = QLineEdit(settings.ollama_model)
        self._hermes_cmd = QLineEdit(settings.hermes_command)
        self._hermes_url = QLineEdit(settings.hermes_base_url)
        self._hermes_key = QLineEdit(settings.hermes_api_key)
        self._hermes_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._hermes_on = QCheckBox("Hermes Agent 사용 (채팅을 Hermes API로 전달)")
        self._hermes_on.setChecked(settings.hermes_enabled)
        form.addRow("Ollama Base URL", self._ollama_url)
        form.addRow("Ollama Model", self._ollama_model)
        form.addRow("Hermes API URL", self._hermes_url)
        form.addRow("Hermes API Key", self._hermes_key)
        form.addRow("Hermes 명령", self._hermes_cmd)
        form.addRow("", self._hermes_on)
        content_lay.addLayout(form)

        if db is not None:
            content_lay.addWidget(self._build_email_box())
            content_lay.addWidget(self._build_ide_box())
            content_lay.addWidget(self._build_project_parents_box())
            content_lay.addWidget(self._build_hermes_control_box())

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if db is not None:
            self._sync_ide_selection_ui()
            self._reload_account_list()

    def _build_email_box(self) -> QGroupBox:
        email_box = QGroupBox("이메일 계정 (Gmail · Naver 등)")
        email_lay = QVBoxLayout(email_box)
        email_lay.addWidget(
            QLabel("IMAP/SMTP로 직접 연결합니다. 일반 로그인 비밀번호 대신 앱 비밀번호를 입력하세요.")
        )
        self._account_list = QListWidget()
        self._account_list.setMaximumHeight(120)
        email_lay.addWidget(self._account_list)

        add_form = QFormLayout()
        self._new_label = QLineEdit()
        self._new_label.setPlaceholderText("예: 개인 Gmail")
        self._new_address = QLineEdit()
        self._new_address.setPlaceholderText("예: you@gmail.com")
        self._new_password = QLineEdit()
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_password.setPlaceholderText("앱/애플리케이션 비밀번호")
        add_form.addRow("표시 이름", self._new_label)
        add_form.addRow("이메일 주소", self._new_address)
        add_form.addRow("비밀번호", self._new_password)
        email_lay.addLayout(add_form)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("계정 추가")
        self._add_btn.clicked.connect(self._add_account)
        self._remove_btn = QPushButton("선택 삭제")
        self._remove_btn.clicked.connect(self._remove_selected_account)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch(1)
        email_lay.addLayout(btn_row)
        return email_box

    def _build_ide_box(self) -> QGroupBox:
        ide_box = QGroupBox("IDE Companion 설정")
        ide_lay = QVBoxLayout(ide_box)
        ide_lay.addWidget(
            QLabel(
                "사용할 IDE를 고르세요. 아이콘·이름을 누르면 선택됩니다. "
                "설치되지 않은 IDE는 안내 창이 뜹니다. "
                "바이브코딩은 Iris 채팅(Hermes→Ollama)으로 진행합니다."
            )
        )
        self._ide_selected = QLabel()
        self._ide_selected.setObjectName("IdeSelectedLabel")
        ide_lay.addWidget(self._ide_selected)

        self._ide_buttons: dict[str, QToolButton] = {}
        grid = QGridLayout()
        grid.setSpacing(8)
        cols = 4
        idx = 0
        for spec in ide_catalog():
            if spec.id == "custom":
                continue
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(40, 40))
            installed = is_ide_installed(spec.id)
            btn.setIcon(ide_icon_for(spec.id))
            status = "" if installed else " (미설치)"
            btn.setText(f"{spec.name}{status}")
            btn.setCheckable(True)
            btn.setMinimumSize(110, 78)
            btn.setToolTip(
                f"{spec.name}" + (" — 설치됨" if installed else " — 설치되지 않음")
            )
            btn.clicked.connect(
                lambda _checked=False, ide_id=spec.id: self._on_ide_picked(ide_id)
            )
            self._ide_buttons[spec.id] = btn
            grid.addWidget(btn, idx // cols, idx % cols)
            idx += 1

        custom_btn = QToolButton()
        custom_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        custom_btn.setIconSize(QSize(40, 40))
        custom_btn.setIcon(ide_icon_for("custom"))
        custom_btn.setText("사용자 지정")
        custom_btn.setCheckable(True)
        custom_btn.setMinimumSize(110, 78)
        custom_btn.setToolTip("실행 파일을 직접 선택")
        custom_btn.clicked.connect(lambda: self._on_ide_picked("custom"))
        self._ide_buttons["custom"] = custom_btn
        grid.addWidget(custom_btn, idx // cols, idx % cols)
        ide_lay.addLayout(grid)
        return ide_box

    def _effective_parents_for_ui(self) -> list[str]:
        if self._project_parents:
            return list(self._project_parents)
        from iris.system.project_ops import default_project_parents

        return [str(p) for p in default_project_parents()]

    def _build_project_parents_box(self) -> QGroupBox:
        box = QGroupBox("프로젝트 검색 부모 폴더")
        lay = QVBoxLayout(box)
        lay.addWidget(
            QLabel(
                "Hermes가 '비슷한 프로젝트 열어'라고 할 때 이 폴더들 아래의 "
                "1depth 하위 폴더만 검색합니다. 비우면(기본값 복원) 내장 후보를 씁니다."
            )
        )
        self._parents_list = QListWidget()
        self._parents_list.setMinimumHeight(110)
        lay.addWidget(self._parents_list)
        for path in self._effective_parents_for_ui():
            self._parents_list.addItem(QListWidgetItem(path))

        btn_row = QHBoxLayout()
        add_btn = QPushButton("폴더 추가")
        add_btn.clicked.connect(self._add_project_parent)
        rem_btn = QPushButton("선택 제거")
        rem_btn.clicked.connect(self._remove_project_parent)
        reset_btn = QPushButton("기본값 복원")
        reset_btn.clicked.connect(self._reset_project_parents)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        return box

    def _parents_from_list_widget(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for i in range(self._parents_list.count()):
            text = (self._parents_list.item(i).text() or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    def _add_project_parent(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "프로젝트 모음 폴더 선택")
        if not path:
            return
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = path
        existing = {p.lower() for p in self._parents_from_list_widget()}
        if resolved.lower() in existing:
            return
        self._parents_list.addItem(QListWidgetItem(resolved))
        self._parents_customized = True
        self._project_parents = self._parents_from_list_widget()

    def _remove_project_parent(self) -> None:
        row = self._parents_list.currentRow()
        if row < 0:
            return
        self._parents_list.takeItem(row)
        self._parents_customized = True
        self._project_parents = self._parents_from_list_widget()

    def _reset_project_parents(self) -> None:
        self._parents_customized = False
        self._project_parents = []
        self._parents_list.clear()
        for path in self._effective_parents_for_ui():
            self._parents_list.addItem(QListWidgetItem(path))

    def _build_hermes_control_box(self) -> QGroupBox:
        box = QGroupBox("Iris ↔ Hermes Control")
        lay = QVBoxLayout(box)
        lay.addWidget(
            QLabel(
                "MCP(iris_get_state / iris_invoke)와 iris-work-start 스킬을 Hermes에 동기화합니다. "
                "도구가 안 보이면 동기화 후 새 채팅을 시작하세요."
            )
        )
        self._sync_status = QLabel(self._load_sync_status_text())
        self._sync_status.setWordWrap(True)
        lay.addWidget(self._sync_status)
        self._sync_btn = QPushButton("지금 MCP/스킬 동기화")
        self._sync_btn.clicked.connect(self._run_hermes_control_sync)
        lay.addWidget(self._sync_btn)
        self._sync_worker = None
        return box

    def _load_sync_status_text(self) -> str:
        try:
            from iris.system.hermes_iris_control_sync import sync_state_path

            path = sync_state_path()
            if not path.is_file():
                return "상태: 아직 동기화하지 않음"
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            ok = bool(data.get("ok"))
            summary = data.get("messages") or []
            line = (summary[0] if summary else "") or (
                "동기화됨" if ok else "동기화 이슈"
            )
            return f"상태: {'OK' if ok else '이슈'} — {line}"
        except Exception:  # noqa: BLE001
            return "상태: 아직 동기화하지 않음"

    def _run_hermes_control_sync(self) -> None:
        from iris.ui.hermes_workers import HermesControlSyncWorker

        if self._sync_worker is not None and self._sync_worker.isRunning():
            return
        base = self._hermes_url.text().strip() or "http://127.0.0.1:8642/v1"
        key = self._hermes_key.text().strip()
        cmd = self._hermes_cmd.text().strip() or "hermes"
        self._sync_btn.setEnabled(False)
        self._sync_status.setText("상태: 동기화 중…")
        worker = HermesControlSyncWorker(
            base, api_key=key, command=cmd, parent=self
        )
        self._sync_worker = worker
        worker.progress.connect(self._sync_status.setText)
        worker.finished_ok.connect(self._on_hermes_control_sync_done)
        worker.start()

    def _on_hermes_control_sync_done(self, ok: bool, summary: str) -> None:
        self._sync_worker = None
        self._sync_btn.setEnabled(True)
        text = summary.strip() or ("동기화 완료" if ok else "동기화 실패")
        self._sync_status.setText(text)
        if ok:
            QMessageBox.information(
                self,
                "Iris Control 동기화",
                "동기화 완료.\nHermes gateway를 재기동했고 MCP 도구가 연결됐습니다.\n"
                "Iris에서 새 채팅을 열어 테스트하세요.",
            )
        else:
            QMessageBox.warning(
                self,
                "Iris Control 동기화",
                "일부 실패:\n" + text[:500],
            )

    def _reload_account_list(self) -> None:
        self._account_list.clear()
        for acc in self._accounts:
            self._account_list.addItem(QListWidgetItem(acc.display_name))

    def _sync_ide_selection_ui(self) -> None:
        ide_id = self._preferred_ide
        for key, btn in self._ide_buttons.items():
            btn.setChecked(key == ide_id)
        spec = get_ide_spec(ide_id)
        name = spec.name if spec else ide_id
        if ide_id == "custom":
            installed = bool(self._ide_exe_path and Path(self._ide_exe_path).is_file())
        else:
            installed = is_ide_installed(ide_id, self._ide_exe_path)
        mark = "설치됨" if installed else "경로 확인 필요"
        self._ide_selected.setText(f"선택: {name} ({mark})")

    def _on_ide_picked(self, ide_id: str) -> None:
        if ide_id == "custom":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "IDE 실행 파일 선택",
                "",
                "Executable (*.exe);;All (*.*)",
            )
            if not path:
                self._sync_ide_selection_ui()
                return
            self._preferred_ide = "custom"
            self._ide_exe_path = path
            self._sync_ide_selection_ui()
            return
        if not is_ide_installed(ide_id, ""):
            show_ide_not_installed_dialog(self, ide_id)
            self._sync_ide_selection_ui()
            return
        self._preferred_ide = ide_id
        self._ide_exe_path = ""
        self._sync_ide_selection_ui()

    def _add_account(self) -> None:
        if self._db is None:
            return
        address = self._new_address.text().strip()
        password = self._new_password.text()
        label = self._new_label.text().strip()
        if not address or "@" not in address:
            QMessageBox.warning(self, "이메일 계정", "올바른 이메일 주소를 입력하세요.")
            return
        if not password:
            QMessageBox.warning(self, "이메일 계정", "앱/애플리케이션 비밀번호를 입력하세요.")
            return
        self._add_btn.setEnabled(False)
        worker = EmailVerifyWorker(address, password, parent=self)
        self._verify_worker = worker
        worker.finished_ok.connect(lambda: self._on_verify_ok(address, password, label))
        worker.failed.connect(self._on_verify_failed)
        worker.start()

    def _on_verify_ok(self, address: str, password: str, label: str) -> None:
        self._add_btn.setEnabled(True)
        self._verify_worker = None
        if self._db is None:
            return
        add_email_account(self._db, address, password, label=label)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()
        self._new_address.clear()
        self._new_password.clear()
        self._new_label.clear()
        QMessageBox.information(self, "이메일 계정", f"{address} 연결 확인됨 — 저장 목록에 추가했습니다.")

    def _on_verify_failed(self, err: str) -> None:
        self._add_btn.setEnabled(True)
        self._verify_worker = None
        QMessageBox.warning(
            self,
            "이메일 계정",
            f"연결에 실패했습니다.\n\n{err[:400]}\n\n"
            "IMAP/SMTP 사용·2단계 인증·앱 비밀번호를 확인하세요.",
        )

    def _remove_selected_account(self) -> None:
        if self._db is None:
            return
        row = self._account_list.currentRow()
        if row < 0 or row >= len(self._accounts):
            return
        acc = self._accounts[row]
        remove_email_account(self._db, acc.id)
        self._accounts = load_email_accounts(self._db)
        self._reload_account_list()

    def _save_profile_ide(self) -> bool:
        if self._db is None:
            return True
        if self._preferred_ide == "custom" and not self._ide_exe_path:
            QMessageBox.warning(
                self,
                "IDE 설정",
                "사용자 지정 IDE는 실행 파일 선택이 필요합니다.",
            )
            return False
        base = self._profile_base
        data = {
            "name": base.name,
            "occupation": base.occupation,
            "hobbies": base.hobbies,
            "interests": base.interests,
            "work_tasks": base.work_tasks,
            "age": base.age,
            "gender": base.gender,
            "residence": base.residence,
            "contact": base.contact,
            "email": base.email,
            "preferred_ide": self._preferred_ide or "cursor",
            "ide_exe_path": self._ide_exe_path if self._preferred_ide == "custom" else "",
            # ponytail: UI에서 제거 — 기존 값 유지 (필요 시 코드/DB에서만)
            "ide_cli_path": self._ide_cli_path,
            "project_root": self._project_root,
            "project_parents": (
                self._parents_from_list_widget() if self._parents_customized else []
            ),
        }
        # 커스텀인데 목록이 비면 거부
        if self._parents_customized and not data["project_parents"]:
            QMessageBox.warning(
                self,
                "프로젝트 검색 부모 폴더",
                "부모 폴더가 비어 있습니다. 폴더를 추가하거나 기본값 복원을 누르세요.",
            )
            return False
        for raw in data["project_parents"]:
            if not Path(raw).expanduser().is_dir():
                QMessageBox.warning(
                    self,
                    "프로젝트 검색 부모 폴더",
                    f"존재하지 않는 폴더입니다:\n{raw}",
                )
                return False
        save_user_profile(self._db, UserProfile(**data))
        self._wiki.sync_email_accounts_index(
            [{"address": a.address, "label": a.label} for a in self._accounts]
        )
        return True

    def _accept(self) -> None:
        if not self._save_profile_ide():
            return
        self._result = LightSettingsSelection(
            ollama_base_url=self._ollama_url.text().strip() or "http://127.0.0.1:11434/v1",
            ollama_model=self._ollama_model.text().strip(),
            hermes_enabled=self._hermes_on.isChecked(),
            hermes_command=self._hermes_cmd.text().strip() or "hermes",
            hermes_base_url=self._hermes_url.text().strip() or "http://127.0.0.1:8642/v1",
            hermes_api_key=self._hermes_key.text().strip(),
        )
        self.accept()

    def selection(self) -> LightSettingsSelection | None:
        return self._result
