"""QWebEngineView hardening for the Iris built-in browser."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

_CHROME_UA_RE = re.compile(r"\s*QtWebEngine/[\d.]+\s*", re.I)
_BRIDGE_JS = (Path(__file__).resolve().parents[2] / "browser" / "_bridge.js").read_text(
    encoding="utf-8"
)
_PROFILE: Any = None
log = logging.getLogger("iris.browser")


def chrome_like_user_agent(raw: str) -> str:
    """Drop QtWebEngine token — many sites treat it as a blocked embedded browser."""
    cleaned = _CHROME_UA_RE.sub(" ", raw or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def browser_profile_path() -> Path:
    override = (os.environ.get("IRIS_BROWSER_PROFILE") or "").strip()
    root = Path(override) if override else Path.home() / ".iris-light" / "browser-profile"
    root.mkdir(parents=True, exist_ok=True)
    return root


def shared_browser_profile() -> Any:
    """One named profile for cookies/session — hang off QApplication, not a view."""
    global _PROFILE
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript

    app = QCoreApplication.instance()
    held = getattr(app, "_iris_browser_profile", None) if app is not None else None
    if held is not None:
        try:
            held.storageName()
            _PROFILE = held
            return held
        except RuntimeError:
            pass
    if _PROFILE is not None:
        try:
            _PROFILE.storageName()
            return _PROFILE
        except RuntimeError:
            _PROFILE = None

    name = (os.environ.get("IRIS_BROWSER_PROFILE_NAME") or "iris-browser").strip() or "iris-browser"
    profile = QWebEngineProfile(name, app)
    profile.setPersistentStoragePath(str(browser_profile_path()))
    profile.setCachePath(str(browser_profile_path() / "cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    default_ua = QWebEngineProfile.defaultProfile().httpUserAgent()
    profile.setHttpUserAgent(chrome_like_user_agent(default_ua))
    profile.setHttpAcceptLanguage("ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7")

    script = QWebEngineScript()
    script.setName("iris-browser-bridge")
    script.setSourceCode(_BRIDGE_JS)
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    profile.scripts().insert(script)
    _PROFILE = profile
    if app is not None:
        app._iris_browser_profile = profile
    return profile


_PAGE_CLS: Any = None


def _page_class() -> Any:
    """One QWebEnginePage subclass — creating a new class per page crashes PyQt."""
    global _PAGE_CLS
    if _PAGE_CLS is not None:
        return _PAGE_CLS
    from PyQt6.QtWebEngineCore import QWebEnginePage

    class IrisWebEnginePage(QWebEnginePage):
        def createWindow(self, kind):  # noqa: N802
            cb = getattr(self, "_on_create_window", None)
            if callable(cb):
                try:
                    adopted = cb()
                except Exception:
                    log.exception("createWindow adopt failed")
                    adopted = None
                if adopted is not None:
                    return adopted
            return super().createWindow(kind)

    _PAGE_CLS = IrisWebEnginePage
    return _PAGE_CLS


def new_browser_page(parent: Any, *, on_create_window: Any | None = None) -> Any:
    page = _page_class()(shared_browser_profile(), parent)
    page._on_create_window = on_create_window
    _wire_page_logging(page)
    return page


def _wire_page_logging(page: Any) -> None:
    def _on_cert(error: Any) -> None:
        # ponytail: accept all — enterprise MITM / local HTTPS; tighten if abuse shows up
        try:
            log.warning("certificateError url=%s", getattr(error, "url", lambda: "")())
        except Exception:
            pass
        try:
            error.acceptCertificate()
        except Exception:
            pass

    def _on_load(ok: bool) -> None:
        try:
            url = str(page.url().toString() or "")
        except Exception:
            url = ""
        if ok:
            log.info("loadFinished ok url=%s", url)
        else:
            log.warning("loadFinished failed url=%s", url)

    def _on_crash(status: Any, code: int) -> None:
        log.error("renderProcessTerminated status=%s code=%s", status, code)

    try:
        page.certificateError.connect(_on_cert)
    except Exception:
        pass
    try:
        page.loadFinished.connect(_on_load)
    except Exception:
        pass
    try:
        page.renderProcessTerminated.connect(_on_crash)
    except Exception:
        pass


def _apply_settings(settings: Any) -> None:
    from PyQt6.QtWebEngineCore import QWebEngineSettings

    attrs = QWebEngineSettings.WebAttribute
    for attr, on in (
        (attrs.JavascriptEnabled, True),
        (attrs.LocalStorageEnabled, True),
        (attrs.LocalContentCanAccessRemoteUrls, True),
        (attrs.JavascriptCanAccessClipboard, True),
        (attrs.JavascriptCanOpenWindows, True),
        (attrs.PluginsEnabled, True),
        (attrs.FullScreenSupportEnabled, True),
        (attrs.PlaybackRequiresUserGesture, False),
        (attrs.WebGLEnabled, True),
        (attrs.Accelerated2dCanvasEnabled, True),
        (attrs.ErrorPageEnabled, True),
        (attrs.FocusOnNavigationEnabled, True),
        (attrs.ScrollAnimatorEnabled, True),
    ):
        try:
            settings.setAttribute(attr, on)
        except Exception:
            pass


def configure_browser_view(view: Any, *, on_create_window: Any | None = None) -> None:
    """Shared profile + Chrome-like UA + settings for real sites."""
    page = new_browser_page(view, on_create_window=on_create_window)
    view.setPage(page)
    _apply_settings(view.settings())
