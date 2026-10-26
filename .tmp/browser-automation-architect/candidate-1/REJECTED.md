# Rejected alternatives (this candidate)

Short note — design shapes rejected while forming candidate-1. Not other arena runners.

1. **Pure Playwright (headless or headed external window)**  
   Strong automation API, but the user does not watch Iris chrome; syncing a second view recreates split ownership. Rejected for the shared-visibility requirement.

2. **Hybrid “Playwright drives, QWebEngine mirrors URL”**  
   Looks like a compromise; actually two writers of “current URL” and inevitable drift on click/type. Rejected as split ownership / two ways to navigate.

3. **Scattered toolbar booleans + per-action handlers** (`_loading`, `_can_back` on the panel; each `browser.*` mutates widgets)`  
   Matches naive Qt demos; fails encode-in-types. Rejected for shallow modules and hand-synced flags.

4. **Theia-first browser tab via IrisIdeBridgePoller**  
   Rejected for v1: bridge latency, bundle rebuild tax, and automation still needs an in-process driver. Optional convenience tab later, not the session owner.

5. **Tool explosion on Hermes MCP** (one MCP tool per verb)**  
   Rejected against grounding thin-MCP rule; Control Surface `browser.invoke` + command registry instead (emulator precedent: actions behind `iris_invoke`).
