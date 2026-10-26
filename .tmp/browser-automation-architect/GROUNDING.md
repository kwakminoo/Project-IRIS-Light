# Phase A grounding — IRIS IDE browser automation

Source: how explorers + explainer (a54d049a).

## Requirements (user)

1. Analyze Agent/MCP; integrate suitable OSS (Playwright etc.)
2. IDE-internal browser tab: URL, refresh, back/forward
3. Agent: web search, click, type, scroll, page navigate
4. User can watch the agent-driven browser in the IDE
5. Tests: YouTube IU night letter; open React docs; scroll current page
6. Keep existing behavior; report constraints + remaining issues briefly

## Existing stack

- Hermes MCP `iris-control`: 3 tools → Control Surface → ActionRegistry (`iris_invoke`)
- Precedent: `emulator.*` in-registry + sibling `mobile-mcp`
- IDE bridge: IrisIdeClient → enqueueFrontend → IrisIdeBridgePoller → Theia (no browser cmds)
- WebEngine: Theia, email, wiki original, diagram card; project preview → OS `webbrowser.open`
- Docs previously rejected Playwright for wiki capture (QWebEngine already present)

## Explainer placement default

- Control Surface owns the contract (`browser.*`)
- Python lazy QWebEngine panel for agent-visible surface
- Optional Theia tab for human convenience only
- Playwright sibling MCP only if CDP depth without Iris chrome is required

## Hard constraints

- `ensure_qt_webengine_ready` before QApplication; lazy-create views
- Never block UI thread waiting on WebEngine/bridge
- Off-UI for blocking browser work (like `emulator.*`)
- Companion child-HWND rules; frameless/DnD boundaries
- Theia changes need `sync_workspace_build` + restart
- Thin MCP: prefer actions behind `iris_invoke`, not tool explosion
