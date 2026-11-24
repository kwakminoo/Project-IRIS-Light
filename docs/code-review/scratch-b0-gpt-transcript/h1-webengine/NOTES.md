# H1 · single QWebEngineView transcript host

Throwaway B0 bakeoff artifact. One Chromium page renders the whole assistant turn from `../shared/sample_turn.json`.

## How to run

From repo root (workspace venv):

```powershell
.venv\Scripts\python.exe docs\code-review\scratch-b0-gpt-transcript\h1-webengine\run.py
```

Headless-ish JS probe (opens a window briefly, then quits):

```powershell
.venv\Scripts\python.exe docs\code-review\scratch-b0-gpt-transcript\h1-webengine\run.py --verify
```

`ensure_qt_webengine_ready()` runs before `QApplication` / `QWebEngineView` import (same Iris pattern). Sample is read only from `shared/sample_turn.json`. Generated HTML is also written to `page.generated.html` for inspection.

## Three checks (observed 2026-11-17)

| Check | Result | Evidence |
|---|---|---|
| Writing edit | **pass** | contenteditable card accepted injected `\n[h1-edit-ok]` |
| Code / Preview toggle | **pass** | Preview hides textarea + shows iframe; Code reverses |
| Inline calculator | **pass** | iframe `계산` with a=5,b=7 → `= 12` |

`--verify` JSON:

```json
{
  "ok": true,
  "probe": {
    "writing": true,
    "codePreview": true,
    "calculator": true,
    "detail": {
      "writing": "contenteditable accepted edit",
      "codePreview": "Code/Preview toggle ok",
      "calculator": "= 12"
    }
  }
}
```

## Friction for Iris T2 (H1 path)

- **Whole row = one WebEngine process surface.** Selection, DnD, native scroll sync, and Qt focus compete with Chromium. Mixing native Qt widgets mid-turn is awkward.
- **Nested iframes (code preview + app)** need `allow-same-origin` (or host bridge) for host↔app JS; sandbox vs XSS tradeoff lands in chat threat model.
- **Markdown → HTML** here is toy. Production needs a safer pipeline (or stick to a constrained subset) and CSP on the host page.
- **Editable writing** lives in the DOM only until you wire a bridge (`QWebChannel` / console message) back to Iris message store. No persistence in this scratch.
- **Cold start / ensure_qt_webengine_ready** still required before any chat that might open a WebEngine turn; first paint cost is Chromium, not QLabel.
- **Styling / theme** must be duplicated into the page CSS (or injected); Iris Qt palette does not auto-apply inside the view.

Screenshots: not captured (optional; verify probe covered the three interactions).
