from __future__ import annotations

import sys
import time
from pathlib import Path

from iris.browser.observation import pack_browser_observation, pack_hermes_result
from iris.browser.session import BrowserSession
from iris.browser.types import BrowserPhase, Navigate, Snapshot

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / ".tmp" / "browser-snapshot"
LOG_PATH = FIXTURE_DIR / "run.log"


def _log(line: str) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _fail(message: str) -> int:
    _log(f"FAILED: {message}")
    return 1


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")
    same = FIXTURE_DIR / "same.html"
    html = FIXTURE_DIR / "snapshot.html"
    same.write_text(
        "<!doctype html><html><body><p>SAME_ORIGIN_SECRET</p>"
        "<button>Inner Submit</button></body></html>",
        encoding="utf-8",
    )
    html.write_text(
        "<!doctype html><html><head><title>IRIS snapshot</title></head><body>"
        "<h1>Login</h1>"
        "<button aria-label='Menu'></button>"
        "<form aria-label='signin'><fieldset><legend>login</legend>"
        "<button type='submit'>Submit</button></fieldset></form>"
        "<form aria-label='signup'><fieldset><legend>signup</legend>"
        "<button type='submit'>Submit</button></fieldset></form>"
        "<label><input type='checkbox' checked> Remember me</label>"
        "<button disabled>Disabled Save</button>"
        "<label for='pw'>Password</label>"
        "<input id='pw' type='password' value='hunter2'>"
        "<iframe id='same' src='same.html' title='same'></iframe>"
        "<div style='height:8000px'></div>"
        "<button id='below-fold'>Below Fold</button>"
        "</body></html>",
        encoding="utf-8",
    )

    try:
        from PyQt6.QtWidgets import QApplication

        from iris.browser._driver import WebEnginePageDriver
        from iris.ui.browser.panel import BrowserPanel
        from iris.ui.qt_bootstrap import ensure_qt_webengine_ready
    except Exception as exc:
        return _fail(f"Qt display missing ({exc})")

    try:
        ensure_qt_webengine_ready()
        app = QApplication.instance() or QApplication(sys.argv)
    except Exception as exc:
        return _fail(f"Qt display missing ({exc})")

    session = BrowserSession()
    panel = BrowserPanel(session)
    panel.resize(800, 400)
    panel.show()
    view = panel.ensure_view()
    view.resize(800, 400)
    driver = WebEnginePageDriver(view)
    session.set_driver(driver)

    url = html.resolve().as_uri()
    r = session.execute(Navigate(url=url))
    if not r.ok:
        panel.close()
        return _fail(f"navigate {r.detail}")

    deadline = time.monotonic() + 12
    snap = r.snapshot
    inner = None
    while time.monotonic() < deadline:
        app.processEvents()
        r = session.execute(Snapshot())
        snap = r.snapshot
        inner = next((n for n in snap.nodes if n.name == "Inner Submit"), None)
        if inner is not None:
            break
        time.sleep(0.2)

    trusted, page_text = pack_browser_observation(session)
    packed = pack_hermes_result(r)
    _log(f"url={snap.url}")
    _log(f"nodes={[(n.ref, n.role, n.name, n.frame, n.in_view, n.disabled, n.checked, n.context) for n in snap.nodes]}")
    _log(f"trusted={trusted}")
    _log(f"page_text={page_text}")

    if set(packed) != {
        "ok",
        "command_kind",
        "detail",
        "trusted",
        "page_text",
        "url",
        "phase",
        "playing",
        "gen",
    }:
        panel.close()
        return _fail(f"packer keys {sorted(packed)}")
    if "IRIS snapshot" in trusted:
        panel.close()
        return _fail("title leaked into trusted")
    if inner is None or not inner.frame.startswith("f"):
        panel.close()
        return _fail(f"iframe button {inner!r}")
    if f"{inner.ref} button Inner Submit frame={inner.frame}" not in page_text:
        panel.close()
        return _fail("iframe PAGE TEXT line")
    below = next((n for n in snap.nodes if n.name == "Below Fold"), None)
    if below is None or below.in_view:
        panel.close()
        return _fail(f"Below Fold in_view {below!r}")
    if f"{below.ref} button Below Fold in_view=false" not in page_text:
        panel.close()
        return _fail("offscreen PAGE TEXT line")
    menu = next((n for n in snap.nodes if n.name == "Menu" and n.role == "button"), None)
    if menu is None:
        panel.close()
        return _fail("aria-label Menu missing")
    submits = [n for n in snap.nodes if n.role == "button" and n.name == "Submit"]
    if len(submits) < 2:
        panel.close()
        return _fail(f"Submit twins {submits!r}")
    ctx_lines = [line for line in page_text.splitlines() if " button Submit ctx=" in line]
    if len(ctx_lines) < 2:
        panel.close()
        return _fail(f"Submit ctx lines {ctx_lines!r}")
    remembered = next((n for n in snap.nodes if n.role == "checkbox" and "Remember" in n.name), None)
    if remembered is None or not remembered.checked:
        panel.close()
        return _fail(f"checkbox {remembered!r}")
    remember_line = next((line for line in page_text.splitlines() if "Remember me" in line), "")
    if "checked" not in remember_line.split():
        panel.close()
        return _fail(f"checked flag missing {remember_line!r}")
    disabled = next((n for n in snap.nodes if n.name == "Disabled Save"), None)
    if disabled is None or not disabled.disabled:
        panel.close()
        return _fail(f"disabled {disabled!r}")
    disabled_line = next((line for line in page_text.splitlines() if "Disabled Save" in line), "")
    if "disabled" not in disabled_line.split():
        panel.close()
        return _fail(f"disabled flag missing {disabled_line!r}")
    password = next((n for n in snap.nodes if n.name == "Password"), None)
    if password is None:
        panel.close()
        return _fail("Password missing")
    if "hunter2" in page_text or "value=" in page_text:
        panel.close()
        return _fail("password value leaked")
    if "SAME_ORIGIN_SECRET" in page_text or "SAME_ORIGIN_SECRET" in (snap.excerpt or ""):
        panel.close()
        return _fail("iframe body leaked")
    if snap.phase == BrowserPhase.FAULTED:
        panel.close()
        return _fail("snapshot faulted")

    panel.close()
    _log("bridge snapshot ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
