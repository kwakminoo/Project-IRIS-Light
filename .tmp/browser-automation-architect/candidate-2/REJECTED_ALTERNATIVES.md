# Rejected alternatives (this candidate)

Short list of shapes **this runner** considered and discarded while locking Theia-sole + Playwright CDP attach. Not other arena candidates.

1. **Python `QWebEngineView` as agent surface** — Explainer default. Rejected here to force a different ownership boundary: document lives in Theia, automation attaches, no second Qt engine for browsing.

2. **Playwright launches its own Chromium; Theia only screencasts** — Strong automation, weak “user drives the same chrome.” Dual input path and Companion HWND risk. Rejected for split ownership of navigation.

3. **Theia widget alone with bridge JS `executeScript` (no Playwright)** — Fewer deps, shallow click/type (no role locators, brittle waits). Rejected for insufficient agent depth on YouTube/React scenarios.

4. **Full Playwright MCP sibling beside `iris-control`** — Matches mobile-mcp precedent for depth, but duplicates click/type and explodes tools. Rejected; fold depth behind `browser.*`.

5. **Raw CDP client without Playwright** — Avoids a dependency; reimplements waits/locators. Rejected; Playwright is the OSS named for attach + locator depth.
