# Mini-player addendum (Experience First gap)

Grounded on SYNTHESIS.md (candidate-1) + how explorers 2026-10-19.

## Problem

`IrisIdeWindow.show_browser()` does `_stack.setCurrentWidget(panel)`. Theia and browser are mutually exclusive. Watching YouTube hides IDE work.

## Shape (domain)

```text
ViewHost = panel | mini   # one QWebEngineView, reparented; never two Chromiums
```

- `BrowserPanel` keeps URL chrome; view slot may be empty while mini holds the view.
- `BrowserMiniPlayer` — frameless `Qt.Tool` child of `IrisIdeWindow`, ~480×270, bottom-right, TOKENS styling, close + “expand to panel”.
- Trigger: YouTube watch URL (`youtube.com/watch`, `youtu.be/`) when leaving browser stack for Theia/welcome, OR `browser.mini_player` / auto on detect after navigate.
- Agent still drives the same view via existing `WebEnginePageDriver` (reparent does not replace driver).

## Commands

Reuse session; add thin commands if needed:

- `MiniPlayer(on: bool)` → control `browser.mini_player` `{on: true|false}`
- Auto: `IrisIdeWindow` when switching away from browser while URL is watch → `session.ensure_mini_player()`

## Non-goals (v1)

- Second WebEngine / Playwright
- Theia-tab browser
- Full PiP OS API

## Verify

- Unit: reparent leaves driver snapshot URL stable
- UI self-check: mini visible + Theia stack current
- Optional live: `IRIS_BROWSER_LIVE=1` YouTube search → click → mini while `show` Theia page
