---
name: iris-browser
description: >
  Drive the Iris IDE in-process browser via Iris Control Surface browser.* actions.
  Use when: open browser, search the web, click a result, type into a page, scroll,
  navigate to a URL, back/forward/reload, take a browser snapshot.
  Do NOT use Playwright MCP or a second Chromium — the user watches the same page.
---

# Iris browser

One visible QWebEngine page inside IRIS IDE. Agent and human chrome share `BrowserSession`.

## Steps

1. `iris_get_state` — read `browser_open`, `browser_url`, `browser_title`, `browser_phase`.
2. `iris_invoke` → `browser.open` if closed.
3. Pick action (all return a snapshot in `result`):

| User intent | Action | Args |
|-------------|--------|------|
| Open browser | `browser.open` | `{}` |
| Go to URL | `browser.navigate` | `{url}` |
| Web search | `browser.search` | `{query}` |
| Click | `browser.click` | `{by: "text"\|"role"\|"css", value\|name\|css, nth?: 0}` |
| Type | `browser.type` | `{by, value\|name, text, clear?: true}` |
| Scroll | `browser.scroll` | `{dy?: 800}` or `{page: "down"\|"up"}` |
| Back / Forward | `browser.back` / `browser.forward` | `{}` |
| Reload | `browser.reload` | `{}` |
| Snapshot | `browser.snapshot` | `{}` |
| Mini player | `browser.mini_player` | `{on: true\|false}` |

## Notes

- Prefer `by=text` or `by=role` from snapshot `landmarks` over guessed CSS.
- `browser.phase` values: `closed` | `opening` | `ready` | `busy` | `faulted`.
- Do not register or call a sibling Playwright MCP for the same clicks.

## Do not

- Do not open an external browser for agent automation.
- Do not use `javascript:` URLs.
- Do not invent click coordinates; use locators from the snapshot.
