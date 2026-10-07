"""업무 학습 직후 — 배운 스킬의 이름·설명·바꿔 넣을 칸을 확인하고 고친다."""

from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from iris.learning.local_learner import describe_steps_text
from iris.learning.skill import Skill, SkillParam
from iris.ui.settings.hud_dialog import configure_hud_dialog
from iris.ui.shared.theme_tokens import TOKENS


class SkillReviewDialog(QDialog):
    def __init__(self, skill: Skill, parent=None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self, title="업무 학습 · 스킬 등록", min_w=520, min_h=420, default_w=600, default_h=560
        )
        self._skill = skill

        root = QVBoxLayout(self)
        root.setSpacing(TOKENS.spacing_md)

        title = QLabel("이 업무를 스킬로 등록할게요")
        title.setObjectName("HudTitle")
        root.addWidget(title)

        root.addWidget(QLabel("스킬 이름 — 채팅에서 이 이름으로 부르면 실행해요"))
        self._name = QLineEdit(skill.name)
        root.addWidget(self._name)

        root.addWidget(QLabel("설명"))
        self._desc = QLineEdit(skill.description)
        root.addWidget(self._desc)

        steps = QLabel(describe_steps_text(skill.steps) or "(단계 없음)")
        steps.setObjectName("HudHint")
        steps.setWordWrap(True)
        root.addWidget(QLabel("배운 단계"))
        root.addWidget(steps)

        # 입력한 글자마다 — 다음에 바꿔 넣을 칸으로 둘지
        self._rows: list[tuple[QCheckBox, QLineEdit, str, str]] = []
        typed = self._typed_examples()
        if typed:
            root.addWidget(QLabel("입력한 글자 중 실행할 때마다 바꿔 넣을 것"))
            grid_w = QWidget()
            grid = QGridLayout(grid_w)
            grid.setContentsMargins(0, 0, 0, 0)
            for r, (example, param) in enumerate(typed):
                box = QCheckBox(f'"{example[:40]}"')
                box.setChecked(param is not None)
                label = QLineEdit(param.label if param else "")
                label.setPlaceholderText("칸 이름 (예: 보낼 메시지, 받는 사람)")
                grid.addWidget(box, r, 0)
                grid.addWidget(label, r, 1)
                self._rows.append((box, label, example, param.name if param else ""))
            root.addWidget(grid_w)

        hint = QLabel(
            "예: '보낼 메시지' 칸을 두면 \"나와의 채팅에 '내일 9시 회의'라고 보내줘\"처럼 "
            "다른 내용으로 실행할 수 있어요."
        )
        hint.setObjectName("HudHint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("등록")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("나중에")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _typed_examples(self) -> list[tuple[str, SkillParam | None]]:
        """(녹화 때 친 글자, 이미 정해진 칸). 칸으로 바뀐 글자는 예시 값으로 되돌려 보여 준다."""
        by_name = {p.name: p for p in self._skill.params}
        out: list[tuple[str, SkillParam | None]] = []
        seen: set[str] = set()
        for s in self._skill.steps:
            if s.kind != "type" or not s.text.strip():
                continue
            # 글자 일부만 칸인 경우('안녕 {when} 봐')도 있다 — 칸마다 한 줄씩.
            # 빠뜨리면 등록할 때 그 칸이 사라진다
            found = [
                by_name[n]
                for n in re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", s.text)
                if n in by_name
            ]
            rows = [(p.example, p) for p in found] if found else [(s.text, None)]
            for example, param in rows:
                if example in seen:
                    continue
                seen.add(example)
                out.append((example, param))
        return out

    def result_name(self) -> str:
        return self._name.text().strip() or self._skill.name

    def result_description(self) -> str:
        return self._desc.text().strip()

    def result_params(self) -> list[SkillParam]:
        params: list[SkillParam] = []
        used: set[str] = set()
        for n, (box, label, example, old_name) in enumerate(self._rows, 1):
            if not box.isChecked():
                continue
            name = old_name or ("text" if n == 1 else f"text{n}")
            while name in used:
                name = f"{name}_{n}"
            used.add(name)
            params.append(
                SkillParam(name=name, label=label.text().strip() or "입력할 내용", example=example)
            )
        return params


class SkillRunDialog(QDialog):
    """채팅으로 스킬을 부를 때 — 넣을 값을 확인하고 실행한다 (마우스·키보드가 움직인다)."""

    def __init__(self, skill: Skill, values: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self, title="업무 실행", min_w=460, min_h=260, default_w=520, default_h=320
        )
        root = QVBoxLayout(self)
        root.setSpacing(TOKENS.spacing_md)
        title = QLabel(f"'{skill.name}' 스킬을 실행할까요?")
        title.setObjectName("HudTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        self._edits: dict[str, QLineEdit] = {}
        if skill.params:
            grid_w = QWidget()
            grid = QGridLayout(grid_w)
            grid.setContentsMargins(0, 0, 0, 0)
            for r, p in enumerate(skill.params):
                grid.addWidget(QLabel(p.label), r, 0)
                edit = QLineEdit(values.get(p.name, ""))
                edit.setPlaceholderText(f"예: {p.example}")
                grid.addWidget(edit, r, 1)
                self._edits[p.name] = edit
            root.addWidget(grid_w)

        hint = QLabel(
            "실행하는 동안 IRIS가 마우스와 키보드를 직접 움직여요. "
            "멈추려면 마우스를 움직이거나 Esc를 누르세요."
        )
        hint.setObjectName("HudHint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText("실행")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        for e in self._edits.values():
            e.textChanged.connect(self._sync_ok)
        self._sync_ok()

    def _sync_ok(self) -> None:
        self._ok.setEnabled(all(e.text().strip() for e in self._edits.values()))

    def values(self) -> dict[str, str]:
        return {k: e.text().strip() for k, e in self._edits.items()}
