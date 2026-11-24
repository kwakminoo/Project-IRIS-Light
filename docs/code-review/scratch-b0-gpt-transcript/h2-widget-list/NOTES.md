# H2 · QScrollArea + per-part QWidget list

Throwaway B0 bakeoff artifact. Native Qt widgets only. No Iris production edits.

## How to run

From repo root (workspace `.venv`):

```powershell
.venv\Scripts\python.exe docs\code-review\scratch-b0-gpt-transcript\h2-widget-list\run.py
```

Automated 3-check smoke (opens window briefly, then exits):

```powershell
.venv\Scripts\python.exe docs\code-review\scratch-b0-gpt-transcript\h2-widget-list\run.py --check
```

Sample is read only from `../shared/sample_turn.json`. WebEngine uses `iris.ui.qt_bootstrap.ensure_qt_webengine_ready` before `QApplication`.

## Observed (2026-11-17)

| Check | Result | Note |
|---|---|---|
| writing edit | PASS | `QPlainTextEdit` writable; `--check` appends `# H2 edit ok` |
| code ↔ preview | PASS | `QTabWidget` tabs `Code` / `Preview`; Preview is `QWebEngineView.setHtml` |
| calculator | PASS | JS sets a=40,b=59, clicks 계산 → `#out` = `= 99` |

`--check` exit 0, printed `PASS`.

## Friction for Iris T2 (if H2 won)

- Every interactive part is a real Qt widget → many children in a long scroll; layout thrash / height negotiation for WebEngine views is on us (no CSS flex).
- Two `QWebEngineView`s per turn that has both code-preview and app; Chromium cost stacks with turn count unless views are deferred/pooled (Iris already warns about constructing WebEngine on UI thread).
- Writing blocks are free-form `QPlainTextEdit`; wiring “edit → next-turn context” needs an Iris-side contract (no HTML form submit).
- Markdown on `QLabel` is OK for the sample; richer GPT-style text (tables, nested lists) may push toward a second WebEngine or a custom painter.
- Tab toggle for code/preview is native and cheap; theming to match chat chrome is manual QSS, not shared with HTML transcript skins.
