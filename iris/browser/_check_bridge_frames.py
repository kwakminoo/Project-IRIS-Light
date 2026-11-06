from __future__ import annotations

import sys
import time
from pathlib import Path

from iris.browser.observation import pack_browser_observation
from iris.browser.session import BrowserSession
from iris.browser.types import BrowserPhase, ByRef, Click, Navigate, Reload, Scroll, Snapshot

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / ".tmp" / "browser-frames"
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
    html = FIXTURE_DIR / "frames.html"
    same = FIXTURE_DIR / "same.html"
    same.write_text(
        "<!doctype html><html><body><p>SAME_ORIGIN_SECRET</p>"
        "<button>Inner Submit</button></body></html>",
        encoding="utf-8",
    )
    html.write_text(
        "<!doctype html><html><head><title>IRIS frames</title></head><body>"
        "<h1>Top Heading</h1><p>UNIQUE_TOP_MARKER</p>"
        "<button id='remove-me'>Remove Target</button>"
        "<iframe id='same' src='same.html' title='same'></iframe>"
        "<iframe id='cross' src='https://example.com' title='cross'></iframe>"
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
    blocked = None
    inner = None
    snap = r.snapshot
    while time.monotonic() < deadline:
        app.processEvents()
        r = session.execute(Snapshot())
        snap = r.snapshot
        inner = next((n for n in snap.nodes if "Inner Submit" in n.name), None)
        blocked = next(
            (fr for fr in snap.frames if "example.com" in (fr.origin or "") and not fr.reachable),
            None,
        )
        if inner is not None and blocked is not None:
            break
        time.sleep(0.2)

    trusted, page_text = pack_browser_observation(session)
    _log(f"url={snap.url}")
    _log(f"nodes={[ (n.ref, n.role, n.name, n.frame, n.in_view) for n in snap.nodes ]}")
    _log(f"frames={[(fr.id, fr.origin, fr.reachable, fr.reason) for fr in snap.frames]}")
    _log(f"trusted={trusted}")
    _log(f"page_text={page_text}")

    if inner is None:
        panel.close()
        return _fail("same-origin iframe button missing")
    if not inner.frame.startswith("f"):
        panel.close()
        return _fail(f"inner frame id {inner.frame!r}")
    if blocked is None:
        panel.close()
        return _fail("cross-origin frame not listed")
    if blocked.reason != "cross_origin":
        panel.close()
        return _fail(f"blocked reason {blocked.reason!r}")
    if "Example Domain" in page_text or "Example Domain" in (snap.excerpt or ""):
        panel.close()
        return _fail("cross-origin body leaked into PAGE TEXT")
    if "SAME_ORIGIN_SECRET" in page_text or "SAME_ORIGIN_SECRET" in (snap.excerpt or ""):
        panel.close()
        return _fail("iframe innerText leaked into excerpt or PAGE TEXT")
    if f"{blocked.id}:{blocked.origin}:cross_origin" not in trusted:
        panel.close()
        return _fail("blocked frame missing from trusted block")

    below = next((n for n in snap.nodes if n.name == "Below Fold"), None)
    if below is None:
        panel.close()
        return _fail("Below Fold button missing")
    scrolled = session.execute(Scroll(ref=below.ref))
    if not scrolled.ok:
        panel.close()
        return _fail(f"scroll-to-ref {scrolled.detail}")
    after = next((n for n in scrolled.snapshot.nodes if n.name == "Below Fold"), None)
    if after is None or not after.in_view:
        panel.close()
        return _fail("scroll-to-ref did not bring node in view")
    _log("scroll-to-ref ok")

    target = next((n for n in session.snapshot().nodes if n.name == "Remove Target"), None)
    if target is None:
        panel.close()
        return _fail("Remove Target missing")
    remove_ref = target.ref
    driver._eval_js(
        "(function(){ var el=document.getElementById('remove-me'); if(el) el.remove(); return true; })()"
    )
    removed = session.execute(Click(target=ByRef(ref=remove_ref)))
    if removed.ok or removed.detail != "stale_ref":
        panel.close()
        return _fail(f"DOM remove click {removed.ok} {removed.detail!r}")
    if removed.snapshot.phase == BrowserPhase.FAULTED:
        panel.close()
        return _fail("DOM remove click faulted")
    _log("click after DOM remove stale_ref ok")

    live = session.execute(Snapshot())
    old = live.snapshot.nodes[0].ref if live.snapshot.nodes else ""
    reloaded = session.execute(Reload())
    if not reloaded.ok:
        panel.close()
        return _fail(f"reload {reloaded.detail}")
    stale = session.execute(Click(target=ByRef(ref=old)))
    if stale.ok or stale.detail != "stale_ref":
        panel.close()
        return _fail(f"reload click {stale.ok} {stale.detail!r}")
    if stale.snapshot.phase == BrowserPhase.FAULTED:
        panel.close()
        return _fail("reload click faulted")
    _log("click after reload stale_ref ok")

    panel.close()
    _log("bridge frames ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
