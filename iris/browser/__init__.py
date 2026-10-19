"""Iris IDE browser automation — BrowserSession command bus."""

from __future__ import annotations

from iris.browser.registry import control_action_names, parse_command
from iris.browser.session import BrowserSession, get_browser_session
from iris.browser.types import (
    BrowserCommand,
    BrowserPhase,
    BrowserResult,
    BrowserSnapshot,
    Navigate,
    Search,
    ViewHost,
)
from iris.browser.youtube import is_youtube_watch_url

__all__ = [
    "BrowserCommand",
    "BrowserPhase",
    "BrowserResult",
    "BrowserSession",
    "BrowserSnapshot",
    "Navigate",
    "Search",
    "ViewHost",
    "control_action_names",
    "get_browser_session",
    "is_youtube_watch_url",
    "parse_command",
]
