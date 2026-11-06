# REA connection and Aside observations

This file records what REA could and could not observe in this session. It is a reference log, not a feature review.

## Connection status

| Item | Result | Evidence |
| --- | --- | --- |
| MCP namespace | `user-rea` reached `ready` | Cursor MCP descriptor for this workspace |
| Server purpose | Reverse-engineering tools for local artifacts, native binaries, managed code, browser pages, and runtimes. Tool results include Evidence, coverage, and limitations. | namespace description returned by tool discovery |
| Skill on disk | `reverse-engineer-anything` from package `rea-agents`, metadata version 42, advertised tool_count 207 | `C:\Users\serin\AppData\Local\npm-cache\_npx\a1722018f28f9df2\node_modules\rea-agents\skills\reverse-engineer-anything\SKILL.md` |
| Upstream project | [morluto/rea](https://github.com/morluto/rea), homepage [rea.tools](https://rea.tools), MIT | fetched README |
| GitHub plugin | `plugin-github-github` failed live discovery | MCP error in this session |
| Aside CLI / `aside mcp` | Not run | no Aside install |

The skill says to skip REA for ordinary source-repository analysis. IRIS source was read with Graphify and file tools, not with REA.

Setup or engine installs were not run. The user forbade install and system-setting changes without approval.

## What REA can legally do here without installing Aside

From the REA README "What you can analyze" table and the connected tool schemas:

| Target | Tool family | Used this session |
| --- | --- | --- |
| Public website | `capture_browser_scenario`, then optional `inspect_web_page` / `analyze_web_bundle` on a loopback CDP endpoint | yes, launch-mode capture of `https://aside.com/` |
| Already-open Chrome with CDP | `list_browser_targets` then `inspect_web_page` | tried `http://127.0.0.1:9222`. `endpoint_unreachable` |
| Installed JS/Electron app | `analyze_javascript_application` on an ASAR or extracted tree | no. No Aside ASAR |
| Installed native binary | `open_binary` plus a Hopper, Ghidra, or IDA provider | no. Aside.exe not present. Native provider not invoked |
| Archive / installer | `open_binary` + `inspect_artifact` on a local `.exe` / `.dmg` | no. Installer was not downloaded |

Downloading the Windows installer would be a new local artifact. That needs approval. This session did not download it.

## Aside install probe (read-only)

PowerShell looked at PATH, `%LOCALAPPDATA%\Programs`, Start Menu, Uninstall registry, App Paths, `SOFTWARE\Aside`, `winget list --name Aside`, running processes, Downloads filenames, and `~\.aside`. No install location, no CLI auth path, no process.

Conclusion: Aside is not installed on this Windows machine. Binary, ASAR, extension, and live-app REA routes are unavailable. History of a past uninstall is unconfirmed.

## Capture of the official homepage

Tool: `user-rea.capture_browser_scenario`.

Inputs:

- `browser.mode`: `launch`
- `executable_path`: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- `headless`: true
- `start_url`: `https://aside.com/`
- one `wait_for_timeout` of 2500 ms
- end artifacts: url, accessibility, screenshot, dom
- events: console, page-errors, network (no bodies)

This launched a provider-owned Chrome with a temporary profile, then terminated it. It did not install Aside and did not change system settings.

Returned Evidence:

| Field | Value |
| --- | --- |
| evidence_id | `ev_9a43ad2fca6d337d79cd5ab01dd615d4b08ddb5ed294cd8de5a7fd148c03f5dd` |
| confidence | observed |
| authority | controlled-replay |
| provider | `rea-playwright-browser-scenario` v1 |
| environment | Chromium 155.0.8059.86 (the launched Chrome, not Aside) |
| duration_ms | 18397 |
| completeness | incomplete (`events` listed as missing_sections even though 186 events were retained) |
| final url | `https://aside.com/` |
| screenshot sha256 | `c2953184de55528721b6e6c54df5b63071d67fc48c4a1663fb941094486ffe94` |
| screenshot media | image/png |
| DOM text bytes | 352004 |
| events retained | 186 |
| event kinds | request 64, response 57, request-finished 56, request-unfinished 8, page-error 1 |
| resource types | script 92, image 57, fetch 15, font 9, stylesheet 6, document 3, other 3 |

Host aggregation from event URLs was empty in the summary script because those URL fields were not plain strings. Treat network hosts as unconfirmed from this capture.

Provider limitations (quoted from the Evidence `limitations` array, partial):

- Artifact identity is unavailable for this observation.
- Event sequence is receipt order, not proven causality.
- Network bodies were not requested.
- Some requests had not finished when capture ended.
- Browser host platform and architecture were not observed.

The accessibility tree of the marketing page included, among other nodes:

- nav: Features, Use cases, Resources, Pricing (`/pricing`)
- Download for Windows
- Y Combinator company link
- heading "The most intelligent AI assistant, but it’s a browser."
- Introducing Aside → `/demo`
- Unlimited capability → `/features/browser-agent`
- illustration text that names Agent tabs, Search, Ask, Local, Guard, GPT-6 Astra High, Recent tasks, artifacts folder

Label the illustration strings `rea-observed` marketing copy. Do not treat "GPT-6 Astra High" as a confirmed shipped model name.

This capture proves the public site renders those claims in a real Chromium. It does not prove the Aside application binary contains the same UI.

A second launch-mode capture of the same URL, from [Aside public REA research](0cdcb973-f09d-453b-928c-a14e207d97dc), also landed on `https://aside.com/` with Chromium 155.0.8059.86. Screenshot sha256 `a98a643d1f7efbf8884f3ff75d2f819c1c2a2238644f05b293d62bfee17a44bb`. Treat that as a second marketing-page observation, not as Aside.exe.

## Skills workflow (not executed as a binary RE)

The bundled skill `reverse-engineer-anything` routes:

1. Installed app or ASAR → `analyze_javascript_application` / `open_binary`.
2. User-owned already-open page → `list_browser_targets`.
3. Agent-driven browser actions → `capture_browser_scenario`.

Step 1 is blocked until Aside is installed or an installer is approved for offline inventory. Step 2 needs a CDP port on a running Aside or Chrome. Step 3 was used only against the public website.

## What would unlock stronger evidence

Ask before doing any of these.

1. Install Aside from [aside.com/download](https://aside.com/download), then a read-only inventory of the install directory.
2. If the install is Chromium-based (official changelog already says Chromium versions), prefer package inventory and extension/resource inspection over a full native decompile.
3. Optional: launch Aside with a documented debug port, then `list_browser_targets` / `inspect_web_page` on its UI origin only.
4. Do not treat marketing JS on aside.com as the desktop app.

A full native decompile of a closed commercial browser is out of scope unless you explicitly expand this investigation.

## Files this log depends on

- REA skill: `...\rea-agents\skills\reverse-engineer-anything\SKILL.md`
- Capture blob: Cursor agent-tools `42cc84d6-95a2-4be7-8d17-fc81cd53fd0f.txt`
- Compact summary: `.tmp/rea-aside-home-summary.json` (local, not part of the report set)
- GitHub README fetch: [morluto/rea](https://github.com/morluto/rea)
- REA docs: [architecture.mermaid](https://raw.githubusercontent.com/morluto/rea/main/docs/architecture.mermaid), [browser-observation.md](https://raw.githubusercontent.com/morluto/rea/main/docs/browser-observation.md)
- Repo skills under `.agents/skills` include `reverse-engineer-anything`. Installing a skill does not register MCP. Star counts on GitHub HTML vs API disagreed. Treat popularity numbers as unconfirmed.
