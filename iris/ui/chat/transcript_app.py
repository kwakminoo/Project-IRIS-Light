"""H1 transcript AppPart: complete-HTML gate + sandboxed iframe card.

Gate rule (require_complete_app_html) lives in ``iris.core.part_contract``.
Re-exported here for existing callers. Fragments without root document
signals are incomplete apps.

displayMode CSS: inline (in-flow), pip (compact floating-style), fullscreen
(expanded in transcript). No OS PiP / T7 Run sandbox.
"""

from __future__ import annotations

import html

from iris.core.message_parts import AppPart, DisplayMode
from iris.core.part_contract import (
    IncompleteAppHtmlError,
    require_complete_app_html,
)
from iris.ui.chat.typography import TOKENS

_t = TOKENS
APP_CARD_CSS = f"""
.app-card {{
  margin: 0 0 0.85rem;
  padding: 12px;
  border: 1px solid {_t.chat_block_border_solid};
  border-radius: {_t.chat_block_radius}px;
  background: {_t.chat_block_bg};
}}
.app-card .app-label {{
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: #64748b;
  margin: 0 0 8px;
}}
.app-card .app-frame {{
  width: 100%;
  height: 280px;
  border: 0;
  border-radius: 8px;
  background: #020617;
  display: block;
  box-sizing: border-box;
}}
.app-card.app-mode-pip {{
  max-width: 320px;
  margin-left: auto;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  border-color: #334155;
}}
.app-card.app-mode-pip .app-frame {{
  height: 180px;
}}
.app-card.app-mode-fullscreen {{
  max-width: none;
  width: 100%;
}}
.app-card.app-mode-fullscreen .app-frame {{
  height: min(70vh, 640px);
  min-height: 420px;
}}
"""


def normalize_display_mode(mode: str | None) -> DisplayMode:
    raw = (mode or "inline").strip().lower()
    if raw in ("inline", "pip", "fullscreen"):
        return raw  # type: ignore[return-value]
    return "inline"


def render_app_part_html(part: AppPart) -> str:
    """Build one sandboxed app iframe card for the H1 transcript page."""
    mode = normalize_display_mode(part.display_mode)
    title = html.escape((part.title or "앱").strip() or "앱")
    # Gate at render so incomplete fragments never become srcdoc apps.
    body = require_complete_app_html(part.html or "")
    srcdoc = html.escape(body, quote=True)
    return (
        f'<section class="app-card app-mode-{mode}" data-part="app" '
        f'data-display-mode="{mode}">'
        f'<div class="app-label">app · {title}</div>'
        f'<iframe class="app-frame" sandbox="allow-scripts allow-same-origin" '
        f'srcdoc="{srcdoc}" title="{title}"></iframe>'
        f"</section>"
    )
