"""사이버스페이스 HUD 테마 — QSS 빌더 및 적용."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QWidget

from iris.ui.theme_tokens import TOKENS


def build_cyberspace_qss() -> str:
    """전역 사이버스페이스 QSS."""
    t = TOKENS
    return f"""
        QWidget {{
            background-color: transparent;
            color: {t.text_primary};
            font-family: {t.font_family};
            font-size: {t.font_size_base};
        }}
        QMainWindow {{
            background-color: {t.void_black};
            border: none;
        }}
        QWidget#FramelessShell {{
            background: transparent;
            border: none;
        }}
        CyberspaceBackground {{
            background-color: {t.void_black};
        }}
        QTextEdit, QListWidget, QLineEdit, QPlainTextEdit {{
            background-color: {t.panel_overlay};
            border: 1px solid {t.border_subtle};
            border-radius: 4px;
            color: {t.text_primary};
            selection-background-color: rgba(37, 99, 235, 0.45);
        }}
        QWidget#LiveActivityPanel,
        QPlainTextEdit#LiveActivityLog {{
            background: transparent;
            background-color: transparent;
            border: none;
        }}
        QPushButton {{
            background-color: {t.accent_primary};
            color: {t.text_primary};
            border: 1px solid {t.border_color};
            border-radius: 4px;
            padding: 6px 12px;
        }}
        QPushButton:hover {{
            background-color: {t.accent_hover};
            border-color: {t.accent_border};
        }}
        QFrame#StatusHeader {{
            background-color: transparent;
            border: none;
            border-radius: 0;
        }}
        QFrame#StatusHeader QLabel {{
            background-color: transparent;
        }}
        QFrame#WorkspacePanel,
        QWidget#AssistantWorkspacePage,
        QWidget#ObsidianWorkspacePage,
        QWidget#ObsidianParticleOrb,
        QWidget#ObsidianDetailPanel,
        QWidget#LeftSidebarPanel,
        QWidget#WindowListPanel,
        QWidget#SidebarUtilityPanel,
        QWidget#SystemMetricsPanel,
        QWidget#WorkspaceActionPanel,
        QWidget#ObsidianNoteListPanel,
        QWidget#ObsidianPreviewPanel,
        QListWidget#ObsidianNoteList,
        QPlainTextEdit#ObsidianPreviewBody,
        QTextBrowser#ObsidianPreviewBody {{
            background: transparent;
            border: none;
        }}
        QTextBrowser#ObsidianPreviewBody {{
            color: {t.text_primary};
            selection-background-color: {t.neon_purple};
        }}
        QLabel#StatusPill {{
            background-color: transparent;
            border: none;
            color: {t.neon_cyan};
            font-size: {t.font_size_hud};
            letter-spacing: 0.5px;
        }}
        QLabel#BackendStatus {{
            color: {t.text_muted};
            font-size: {t.font_size_micro};
        }}
        QLabel#TtsStatus {{
            color: {t.text_secondary};
            font-size: {t.font_size_hud};
        }}
        QLabel#ModelStatus {{
            color: {t.text_accent};
            font-weight: 500;
            font-size: {t.font_size_hud};
            letter-spacing: 0.8px;
        }}
        QSplitter::handle {{
            background: transparent;
            margin: 0;
            border: none;
            width: 0px;
            height: 0px;
            max-width: 0px;
            max-height: 0px;
        }}
        QSplitter::handle:hover {{
            background: transparent;
        }}
        QScrollBar:vertical,
        QScrollBar:horizontal {{
            width: 0px;
            height: 0px;
            background: transparent;
            margin: 0;
        }}
        QScrollArea#PanelScrollArea QScrollBar:vertical {{
            width: 6px;
            background: transparent;
            margin: 2px 0;
        }}
        QScrollArea#PanelScrollArea QScrollBar::handle:vertical {{
            background: rgba(148, 163, 184, 0.18);
            border-radius: 3px;
            min-height: 24px;
        }}
        QScrollArea#PanelScrollArea:hover QScrollBar::handle:vertical {{
            background: rgba(56, 189, 248, 0.45);
        }}
        QScrollArea#PanelScrollArea QScrollBar::add-line:vertical,
        QScrollArea#PanelScrollArea QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QPushButton#WinCtrl {{
            background-color: transparent;
            border: 1px solid {t.border_subtle};
            padding: 0;
            min-width: 34px;
            max-width: 34px;
            min-height: 28px;
            max-height: 28px;
            font-size: 14px;
            font-weight: 400;
            border-radius: 3px;
        }}
        QPushButton#WinCtrl:hover {{
            background-color: {t.accent_primary};
            border-color: {t.accent_border};
        }}
        QPushButton#WinCtrl:pressed {{
            background-color: rgba(30, 58, 138, 0.5);
        }}
        QLabel#DragTitle {{
            font-weight: 400;
            font-size: 25px;
            letter-spacing: 3px;
            color: {t.text_accent};
            background: transparent;
            border: none;
            padding: 0;
            margin: 0;
        }}
        QWidget#DragTab {{
            background: transparent;
            border-top: {t.border_width}px solid {t.border_subtle};
            border-bottom: {t.border_width}px solid {t.border_subtle};
        }}
        QLabel#PanelTitle,
        QLabel#SidebarTitle,
        QLabel#HudSectionTitle {{
            font-weight: 500;
            font-size: {t.font_size_hud};
            letter-spacing: 1.2px;
            color: {t.text_hud_label};
            background: transparent;
        }}
        QPushButton#HudModeButton {{
            background: transparent;
            border: 1px solid {t.border_color};
            border-radius: 3px;
            padding: 8px 10px;
            font-weight: 500;
            font-size: {t.font_size_hud};
            letter-spacing: 0.6px;
            color: {t.text_accent};
        }}
        QPushButton#HudModeButton:hover {{
            background: {t.accent_primary};
            border-color: {t.neon_cyan};
            color: {t.text_primary};
        }}
        QPushButton#HudModeButton[active="true"] {{
            background: rgba(37, 99, 235, 0.35);
            border-color: {t.neon_cyan};
            color: {t.neon_cyan};
        }}
        QPushButton#HudIconButton {{
            background: transparent;
            border: 1px solid {t.border_color};
            border-radius: 3px;
            padding: 0;
            min-width: 40px;
            max-width: 40px;
            min-height: 40px;
            max-height: 40px;
        }}
        QPushButton#HudIconButton:hover {{
            background: {t.accent_primary};
            border-color: {t.neon_cyan};
        }}
        QPushButton#HudIconButton[active="true"] {{
            background: rgba(37, 99, 235, 0.35);
            border-color: {t.neon_cyan};
        }}
        QPushButton#IdeActivityBackButton {{
            background: transparent;
            border: none;
            border-radius: 0;
            padding: 0;
            color: {t.text_secondary};
            font-size: 18px;
            font-weight: 600;
        }}
        QPushButton#IdeActivityBackButton:hover {{
            background: rgba(37, 99, 235, 0.18);
            color: {t.neon_cyan};
        }}
        QPushButton#IdeActivityBackButton:pressed {{
            background: rgba(37, 99, 235, 0.32);
            color: {t.neon_cyan};
        }}
        QPushButton#IdeActivityBackButton:focus {{
            border: 1px solid {t.neon_cyan};
            background: rgba(37, 99, 235, 0.12);
            color: {t.neon_cyan};
        }}
        QProgressBar#HudMetricBar {{
            background: {t.metric_track};
            border: none;
            border-radius: 2px;
            height: 6px;
            text-align: right;
            color: {t.text_secondary};
            font-size: {t.font_size_micro};
        }}
        QProgressBar#HudMetricBar::chunk {{
            border-radius: 2px;
        }}
        QWidget#UiOverlay {{
            background: transparent;
            border: none;
        }}
        QWidget#OrbLayoutSpacer {{
            background: transparent;
            border: none;
        }}
        QPushButton#AlertActionButton {{
            background: transparent;
            border: none;
            color: {t.text_secondary};
            padding: 4px 8px;
            font-size: {t.font_size_micro};
        }}
        QPushButton#AlertActionButton:hover {{
            color: {t.text_accent};
            background: transparent;
        }}
        QWidget#UnifiedMonitorPanel,
        QWidget#NotificationPanel {{
            background: transparent;
            border: none;
        }}
        QWidget#SectionHeader {{
            background: transparent;
            border: none;
        }}
        QFrame#SectionUnderline {{
            background: {t.border_color};
            border: none;
            max-height: 1px;
        }}
        QTextEdit#ChatLog,
        QWidget#ChatPanel,
        QWidget#ChatInputArea,
        QWidget#ChatInputBar,
        QWidget#ChatInputShell {{
            background: transparent;
            border: none;
        }}
        QLineEdit#ChatInput {{
            background: transparent;
            border: none;
        }}
        QWidget#NotificationPanel QListWidget {{
            background: transparent;
            border: none;
        }}
        QFrame#HudWindowRow {{
            background: transparent;
            border: none;
            border-radius: 0;
        }}
        QFrame#HudWindowRow:hover {{
            background: {t.panel_hover};
        }}
        QFrame#HudWindowRow[active="true"] {{
            border-left: 2px solid {t.neon_cyan};
            background: rgba(34, 211, 238, 0.08);
        }}
        QFrame#GlassPanel {{
            background-color: {t.panel_background};
            border: {t.border_width}px solid {t.panel_border};
            border-radius: {t.radius_md}px;
        }}
        QFrame#TopStatusHeader {{
            background: transparent;
            border: none;
            border-bottom: 1px solid {t.border_subtle};
        }}
        QWidget#TopStatusBlock,
        QWidget#TopStatusPrimaryRow,
        QWidget#TopStatusBackendRow,
        QWidget#DragTabStatusColumn {{
            background: transparent;
            border: none;
        }}
        QLabel#StatusChipPrefix {{
            color: {t.text_muted};
            font-size: {t.font_size_micro};
            letter-spacing: 0.6px;
            font-weight: 600;
        }}
        QLabel#StatusChipValue {{
            color: {t.text_secondary};
            font-size: {t.font_size_caption};
            font-weight: 500;
        }}
        QLabel#StatusChipValueMono {{
            color: {t.text_accent};
            font-size: {t.font_size_caption};
            font-weight: 500;
        }}
        QLabel#HudMetricName {{
            color: {t.text_hud_label};
            font-size: {t.font_size_caption};
            letter-spacing: 0.8px;
            font-weight: 600;
        }}
        QLabel#HudMetricValue {{
            color: {t.text_primary};
            font-size: {t.font_size_caption};
            font-weight: 600;
        }}
        QLabel#PanelEmptyHint {{
            color: {t.text_muted};
            font-size: {t.font_size_caption};
        }}
        QWidget#CommandDock {{
            background: transparent;
            border: none;
            border-top: 1px solid {t.border_subtle};
            padding-top: {t.spacing_sm}px;
        }}
        QLineEdit#CommandDockInput {{
            background-color: {t.panel_overlay};
            border: 1px solid {t.panel_border};
            border-radius: {t.radius_md}px;
            padding: 8px 12px;
            font-size: {t.font_size_input};
            color: {t.text_primary};
        }}
        QLineEdit#CommandDockInput:focus {{
            border-color: {t.accent_border};
        }}
        QPushButton#CommandDockSendButton {{
            background-color: {t.accent_primary};
            border: 1px solid {t.accent_border};
            border-radius: {t.radius_md}px;
            font-size: {t.font_size_caption};
            font-weight: 600;
            letter-spacing: 0.4px;
        }}
        QPushButton#CommandDockSendButton:hover:enabled {{
            background-color: {t.accent_hover};
        }}
        QPushButton#CommandDockSendButton:disabled {{
            background-color: rgba(15, 23, 42, 0.8);
            color: {t.disabled};
            border-color: {t.border_subtle};
        }}
        QPushButton#CommandDockIdeButton {{
            background: transparent;
            border: 1px solid {t.border_color};
            border-radius: {t.radius_md}px;
            font-size: {t.font_size_caption};
            font-weight: 600;
            letter-spacing: 0.8px;
            color: {t.text_accent};
        }}
        QPushButton#CommandDockIdeButton:hover {{
            background: {t.accent_primary};
            border-color: {t.neon_cyan};
        }}
        QPushButton#CommandDockIdeButton[active="true"] {{
            background: rgba(37, 99, 235, 0.35);
            border-color: {t.neon_cyan};
            color: {t.neon_cyan};
        }}
        QLabel#CommandDockVoiceLabel {{
            color: {t.text_muted};
            font-size: {t.font_size_micro};
            letter-spacing: 0.4px;
        }}
        QListWidget#AlertsList {{
            background: transparent;
            border: none;
            font-size: {t.font_size_caption};
        }}
        QListWidget#AlertsList::item {{
            padding: 6px 4px;
            border-bottom: 1px solid {t.border_subtle};
        }}
        QListWidget#AlertsList::item:selected {{
            background: {t.panel_hover};
            color: {t.text_primary};
        }}
        QPushButton#AlertActionButton:disabled {{
            color: {t.disabled};
        }}
        QPushButton#AlertActionButton:pressed {{
            color: {t.neon_cyan};
        }}
        QPushButton#HudWindowClose {{
            background: transparent;
            border: none;
            color: {t.text_muted};
        }}
        QPushButton#HudWindowClose:hover {{
            color: {t.error};
        }}
    """


def apply_cyberspace_theme(widget: QWidget) -> None:
    """팔레트 + QSS 적용."""
    t = TOKENS
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t.void_black))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t.text_primary))
    pal.setColor(QPalette.ColorRole.Base, QColor(6, 14, 28))
    pal.setColor(QPalette.ColorRole.Text, QColor(t.text_primary))
    pal.setColor(QPalette.ColorRole.Button, QColor(8, 16, 32))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t.text_primary))
    widget.setPalette(pal)
    widget.setStyleSheet(build_cyberspace_qss())
