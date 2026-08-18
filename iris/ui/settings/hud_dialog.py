"""설정/프로필 다이얼로그용 Iris HUD 크롬 — 메인 화면 토큰과 맞춤."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from iris.ui.shared.theme_tokens import TOKENS


def hud_dialog_qss() -> str:
    t = TOKENS
    return f"""
        QDialog#IrisHudDialog {{
            background-color: {t.space_deep};
            color: {t.text_primary};
            font-family: {t.font_family};
            font-size: {t.font_size_body};
        }}
        QDialog#IrisHudDialog QLabel {{
            background: transparent;
            color: {t.text_primary};
        }}
        QLabel#HudDialogTitle {{
            color: {t.text_accent};
            font-size: {t.font_size_title};
            font-weight: 600;
            letter-spacing: 0.04em;
            padding: 2px 0 4px 0;
        }}
        QLabel#HudDialogHint {{
            color: {t.text_secondary};
            font-size: {t.font_size_caption};
        }}
        QLabel#HudFormLabel {{
            color: {t.text_hud_label};
            font-size: {t.font_size_caption};
            min-width: 148px;
            max-width: 220px;
        }}
        QScrollArea#HudDialogScroll {{
            background: transparent;
            border: none;
        }}
        QWidget#HudDialogScrollInner {{
            background: transparent;
        }}
        QGroupBox {{
            background-color: {t.panel_background};
            border: 1px solid {t.panel_border};
            border-radius: {t.radius_md}px;
            margin-top: 14px;
            padding: 14px 12px 12px 12px;
            font-size: {t.font_size_heading};
            font-weight: 600;
            color: {t.text_accent};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 6px;
            color: {t.neon_cyan};
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QComboBox {{
            background-color: {t.panel_overlay};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: {t.radius_sm}px;
            padding: 7px 9px;
            selection-background-color: rgba(37, 99, 235, 0.45);
            min-height: 20px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
            border: 1px solid {t.accent_border};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QCheckBox {{
            color: {t.text_primary};
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border: 1px solid {t.border_color};
            border-radius: 2px;
            background: {t.panel_overlay};
        }}
        QCheckBox::indicator:checked {{
            background: {t.neon_blue};
            border-color: {t.neon_cyan};
        }}
        QPushButton {{
            background-color: {t.accent_primary};
            color: {t.text_primary};
            border: 1px solid {t.border_color};
            border-radius: {t.radius_sm}px;
            padding: 7px 14px;
            min-height: 22px;
        }}
        QPushButton:hover {{
            background-color: {t.accent_hover};
            border-color: {t.accent_border};
        }}
        QToolButton {{
            background-color: {t.panel_overlay};
            color: {t.text_primary};
            border: 1px solid {t.border_subtle};
            border-radius: {t.radius_md}px;
            padding: 8px 6px;
        }}
        QToolButton:checked {{
            border: 1px solid {t.accent_border};
            background-color: {t.panel_hover};
        }}
        QToolButton:hover {{
            border-color: {t.neon_blue};
        }}
        QDialogButtonBox QPushButton {{
            min-width: 88px;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {t.border_color};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """


def configure_hud_dialog(
    dialog: QDialog,
    *,
    title: str,
    min_w: int = 720,
    min_h: int = 640,
    default_w: int = 820,
    default_h: int = 760,
) -> None:
    """창 크기·타이틀·HUD QSS. 내용이 잘리지 않도록 기본 크기를 넉넉히."""
    dialog.setObjectName("IrisHudDialog")
    dialog.setWindowTitle(title)
    dialog.setWindowFlags(
        dialog.windowFlags()
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowMinimizeButtonHint
    )
    dialog.setMinimumSize(min_w, min_h)
    dialog.resize(default_w, default_h)
    dialog.setSizeGripEnabled(True)
    dialog.setStyleSheet(hud_dialog_qss())


def make_title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("HudDialogTitle")
    return lab


def make_hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("HudDialogHint")
    lab.setWordWrap(True)
    lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return lab


def make_form_label(text: str) -> QLabel:
    """긴 한글 라벨이 잘리지 않도록 래핑 + 최소 폭."""
    lab = QLabel(text)
    lab.setObjectName("HudFormLabel")
    lab.setWordWrap(True)
    lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    lab.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
    return lab


def configure_form(form: QFormLayout) -> None:
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setHorizontalSpacing(TOKENS.spacing_md)
    form.setVerticalSpacing(TOKENS.spacing_sm)
    form.setContentsMargins(0, 0, 0, 0)


def make_scroll_body() -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setObjectName("HudDialogScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    inner = QWidget()
    inner.setObjectName("HudDialogScrollInner")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(4, 4, 12, 8)
    lay.setSpacing(TOKENS.spacing_lg)
    scroll.setWidget(inner)
    return scroll, lay


def _confirm_qss(*, accent: str) -> str:
    t = TOKENS
    return (
        hud_dialog_qss()
        + f"""
        QDialog#IrisHudConfirm {{
            background: transparent;
        }}
        QFrame#HudConfirmShell {{
            background-color: {t.space_deep};
            border: 1px solid {accent};
            border-radius: {t.radius_lg}px;
        }}
        QLabel#HudConfirmEyebrow {{
            color: {accent};
            font-size: {t.font_size_micro};
            font-weight: 700;
            letter-spacing: 0.14em;
        }}
        QLabel#HudConfirmBadge {{
            color: {t.void_black};
            background-color: {accent};
            border-radius: {t.radius_sm}px;
            padding: 3px 8px;
            font-size: {t.font_size_micro};
            font-weight: 700;
            letter-spacing: 0.06em;
        }}
        QLabel#HudConfirmBody {{
            color: {t.text_primary};
            font-size: {t.font_size_body};
            font-weight: 600;
        }}
        QLabel#HudConfirmHint {{
            color: {t.text_secondary};
            font-size: {t.font_size_caption};
        }}
        QPushButton#HudConfirmCancel {{
            background-color: transparent;
            color: {t.text_secondary};
            border: 1px solid {t.border_subtle};
            min-width: 88px;
        }}
        QPushButton#HudConfirmCancel:hover {{
            color: {t.text_primary};
            border-color: {t.border_color};
            background-color: {t.panel_overlay};
        }}
        QPushButton#HudConfirmOk {{
            background-color: {t.accent_primary};
            color: {t.text_primary};
            border: 1px solid {accent};
            min-width: 96px;
            font-weight: 600;
        }}
        QPushButton#HudConfirmOk:hover {{
            background-color: {t.accent_hover};
            border-color: {t.neon_cyan};
        }}
        """
    )


def run_hud_confirm(
    parent: QWidget | None,
    *,
    title: str,
    body: str,
    hint: str,
    badge: str,
    accent: str | None = None,
    ok_text: str = "선택",
    cancel_text: str = "취소",
    default_ok: bool = False,
) -> bool:
    """컴팩트 Iris HUD 확인창. True면 확인."""
    accent_color = accent or TOKENS.neon_cyan
    dlg = QDialog(parent)
    dlg.setObjectName("IrisHudConfirm")
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setWindowFlags(
        (dlg.windowFlags() | Qt.WindowType.FramelessWindowHint)
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    dlg.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    dlg.setFixedWidth(420)
    dlg.setStyleSheet(_confirm_qss(accent=accent_color))

    root = QVBoxLayout(dlg)
    root.setContentsMargins(0, 0, 0, 0)
    shell = QFrame(dlg)
    shell.setObjectName("HudConfirmShell")
    root.addWidget(shell)

    lay = QVBoxLayout(shell)
    lay.setContentsMargins(20, 18, 20, 16)
    lay.setSpacing(TOKENS.spacing_sm)

    top = QHBoxLayout()
    top.setSpacing(TOKENS.spacing_sm)
    eye = QLabel("MODEL NOTICE")
    eye.setObjectName("HudConfirmEyebrow")
    top.addWidget(eye, 0, Qt.AlignmentFlag.AlignVCenter)
    top.addStretch(1)
    badge_lab = QLabel(badge.upper())
    badge_lab.setObjectName("HudConfirmBadge")
    badge_lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    top.addWidget(badge_lab, 0)
    lay.addLayout(top)

    body_lab = QLabel(body)
    body_lab.setObjectName("HudConfirmBody")
    body_lab.setWordWrap(True)
    lay.addWidget(body_lab)

    hint_lab = QLabel(hint)
    hint_lab.setObjectName("HudConfirmHint")
    hint_lab.setWordWrap(True)
    lay.addWidget(hint_lab)

    btns = QHBoxLayout()
    btns.setSpacing(TOKENS.spacing_sm)
    btns.addStretch(1)
    cancel = QPushButton(cancel_text)
    cancel.setObjectName("HudConfirmCancel")
    cancel.setCursor(Qt.CursorShape.PointingHandCursor)
    cancel.setDefault(not default_ok)
    cancel.clicked.connect(dlg.reject)
    ok = QPushButton(ok_text)
    ok.setObjectName("HudConfirmOk")
    ok.setCursor(Qt.CursorShape.PointingHandCursor)
    ok.setAutoDefault(False)
    ok.setDefault(default_ok)
    ok.clicked.connect(dlg.accept)
    btns.addWidget(cancel)
    btns.addWidget(ok)
    lay.addLayout(btns)

    return dlg.exec() == QDialog.DialogCode.Accepted


if __name__ == "__main__":
    qss = hud_dialog_qss()
    assert "IrisHudDialog" in qss or "QDialog#IrisHudDialog" in qss
    assert TOKENS.neon_cyan in qss
    assert "min-width: 148px" in qss
    assert "IrisHudConfirm" in _confirm_qss(accent=TOKENS.warning)
    print("hud_dialog ok")
