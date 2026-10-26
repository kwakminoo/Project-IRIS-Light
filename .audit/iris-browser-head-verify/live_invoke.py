"""Drive the running IRIS HUD through /v1/invoke. Rerun: python -m this file from repo root."""

from __future__ import annotations

import json
import time
from pathlib import Path

from iris.mcp.iris_control_stdio import _http

OUT = Path(__file__).resolve().parent
STEPS = []


def state() -> dict:
    st = _http("GET", "/v1/state")
    res = st.get("result") if isinstance(st.get("result"), dict) else {}
    return {
        "ok": st.get("ok"),
        "error": st.get("error"),
        "ui_mode": res.get("ui_mode"),
        "workspace_mode": res.get("workspace_mode"),
        "browser_open": res.get("browser_open"),
        "browser_url": res.get("browser_url"),
        "browser_title": res.get("browser_title"),
        "browser_phase": res.get("browser_phase"),
        "browser_playing": res.get("browser_playing"),
        "mini_player": res.get("mini_player"),
        "ide_attached": res.get("ide_attached"),
        "hermes_online": res.get("hermes_online"),
    }


def invoke(action: str, args: dict | None = None) -> dict:
    return _http("POST", "/v1/invoke", {"action": action, "args": args or {}})


def step(name: str, action: str, args: dict | None = None) -> dict:
    t0 = time.time()
    raw = invoke(action, args)
    row = {
        "name": name,
        "action": action,
        "ok": raw.get("ok"),
        "error": raw.get("error"),
        "elapsed_s": round(time.time() - t0, 2),
        "result_url": (raw.get("result") or {}).get("url") if isinstance(raw.get("result"), dict) else None,
        "state": state(),
    }
    STEPS.append(row)
    print(f"{name}: ok={row['ok']} err={row['error']} url={row['state'].get('browser_url')} mini={row['state'].get('mini_player')}", flush=True)
    return row


def grab(label: str) -> None:
    path = OUT / f"{label}.png"
    try:
        from PIL import ImageGrab

        ImageGrab.grab().save(path)
        print(f"shot {path.name}", flush=True)
    except Exception as exc:
        print(f"shot skip {label}: {exc}", flush=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    STEPS.append({"name": "baseline", "state": state()})
    print("baseline", STEPS[-1]["state"], flush=True)
    grab("00-home")

    for i in range(3):
        step(f"open-{i+1}", "browser.open")
        grab(f"01-open-{i+1}")
        step(f"home-{i+1}", "workspace.open_assistant")
        grab(f"02-home-{i+1}")

    step("open-nav", "browser.open")
    step("navigate-example", "browser.navigate", {"url": "https://example.com"})
    grab("03-example")
    step("reload", "browser.reload")
    step("search-google", "browser.search", {"query": "example domain", "engine": "google"})
    grab("04-search")
    step("back", "browser.back")
    step("forward", "browser.forward")

    yt = step("youtube-play", "browser.search", {"query": "never gonna give you up", "engine": "youtube", "play": True})
    grab("05-youtube")
    time.sleep(2)
    STEPS.append({"name": "youtube-settle", "state": state()})
    grab("05b-youtube-settle")

    mini_on = step("mini-on", "browser.mini_player", {"on": True})
    grab("06-mini-on")
    mini_off = step("mini-off", "browser.mini_player", {"on": False})
    grab("07-mini-off")

    step("to-home-persist", "workspace.open_assistant")
    grab("08-home-after-yt")
    persist = state()
    STEPS.append({"name": "persist-home", "state": persist})

    ide = step("ide-enter", "ide.enter_companion")
    grab("09-ide")
    ide_browser = step("ide-browser-open", "browser.open")
    grab("10-ide-browser")

    report = {
        "head": "7ec66566505d9b002927dce80fd0f8bb358618af",
        "youtube_ok": bool(yt.get("ok")),
        "mini_on_ok": bool(mini_on.get("ok")),
        "mini_off_ok": bool(mini_off.get("ok")),
        "ide_ok": bool(ide.get("ok")),
        "ide_browser_ok": bool(ide_browser.get("ok")),
        "persist_playing": persist.get("browser_playing"),
        "persist_mini": persist.get("mini_player"),
        "persist_url": persist.get("browser_url"),
        "steps": STEPS,
    }
    (OUT / "live_invoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote live_invoke.json", flush=True)
    return 0 if yt.get("ok") and mini_on.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
