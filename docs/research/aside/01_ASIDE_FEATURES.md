# Aside feature inventory

Evidence labels in this file are `official`, `changelog`, `rea-observed`, `third-party`, `inferred`, or `unconfirmed`. A row without a local Aside install is not a runtime proof of the shipped app.

Sources used:

- [Aside home](https://aside.com/)
- [Download](https://aside.com/download)
- [Browser agent](https://aside.com/features/browser-agent)
- [Memory marketing](https://aside.com/features/memory)
- [Password manager marketing](https://aside.com/features/password-manager)
- [Pricing](https://aside.com/pricing)
- [Get started](https://docs.aside.com/help/get-started)
- [Browser basics](https://docs.aside.com/help/browser-basics)
- [Run tasks](https://docs.aside.com/help/tasks)
- [Side panel](https://docs.aside.com/help/side-panel)
- [Ultrabrowse](https://docs.aside.com/help/ultrabrowse)
- [Manage memory](https://docs.aside.com/help/memory)
- [Password manager help](https://docs.aside.com/help/password-manager)
- [Agent permissions](https://docs.aside.com/help/security)
- [CLI, MCP, and REPL](https://docs.aside.com/help/developers)
- [Components changelog](https://docs.aside.com/changelog/components)
- [Native changelog](https://docs.aside.com/changelog/native)
- REA `capture_browser_scenario` of `https://aside.com/` on 2026-10-27, evidence id `ev_9a43ad2fca6d337d79cd5ab01dd615d4b08ddb5ed294cd8de5a7fd148c03f5dd`

This machine does not have Aside installed. Features below are product claims and help-center behavior, not a live walkthrough of the binary.

## Product identity

Aside is a standalone AI browser for macOS and Windows. The help center states there is no separate minimum browser version because Aside is the browser. Official, [Get started](https://docs.aside.com/help/get-started).

The download page states macOS uses a `.dmg` and Windows uses an executable installer. Official, [Download](https://aside.com/download).

macOS 15.0 or later is the documented floor. Official, [Get started](https://docs.aside.com/help/get-started). Windows 10 appears as a supported surface in the native changelog (translucent backgrounds). Changelog, [Native changelog](https://docs.aside.com/changelog/native). A Windows ARM64 build is official in that same changelog.

Y Combinator backing is linked from the public homepage. `rea-observed` on the marketing accessibility tree (`link "Backed by Y Combinator"` → `https://www.ycombinator.com/companies/aside`).

## Daily browser

| Feature | What the docs say | Evidence |
| --- | --- | --- |
| Ask AI | New-tab omnibox has Search and Ask AI. Task composers use `Ask AI a task, @ for context`. `Cmd/Ctrl+E` starts Ask Aside. | official, [Browser basics](https://docs.aside.com/help/browser-basics) |
| Split tabs | Two pages stay visible. Shortcuts `Cmd/Ctrl+Shift+\` and `Cmd/Ctrl+Shift+-`. | official, [Browser basics](https://docs.aside.com/help/browser-basics) |
| Side panel | Start a task from the current page and keep that page attached. Drafts are stored by page context. | official, [Side panel](https://docs.aside.com/help/side-panel) |
| Lasso and selection | Text defaults Summarize and Translate. Lasso defaults Copy code and Search image. Templates `{text}`, `{code}`, `{image}`. Changelog treats Lasso as an extension. | official + changelog |
| Agent Tabs | Tabs used by the agent, MCP, or CLI group in the sidebar. Take over lets a person use the tab as a normal page. | changelog, [Native changelog](https://docs.aside.com/changelog/native) |
| Profiles | One Aside account can own multiple Chromium profiles. Profiles can copy bookmarks, cookies, history, and extensions once. | changelog |
| Extensions | Chrome Web Store link on the extensions page. Profiles copy extensions. | changelog |
| Import | Onboarding can import browsing history, cookies, and bookmarks. Safari uses a ZIP export. | official, [Get started](https://docs.aside.com/help/get-started) |
| PDF and Office | Changelog names a shared PDFium runtime for PDFs and skill workflows for Office files. | changelog |

The marketing homepage illustration, captured by REA, also shows Search, Ask, Local, Guard, Recent tasks, Agent tabs, and an artifacts folder. That is `rea-observed` marketing UI copy, not a proof that those controls exist with those labels in the installed app.

## Agent tasks

| Feature | What the docs say | Evidence |
| --- | --- | --- |
| Task page | Longer work across sites, files, search, autofill, and approvals. | official, [Run tasks](https://docs.aside.com/help/tasks) |
| Default vs Incognito | Default uses the normal profile. Incognito does not keep normal profile state. | official, [Run tasks](https://docs.aside.com/help/tasks) |
| Permission modes | Read only, Guard (default), Full access. Guard asks before leaving approved folders. | official, [Agent permissions](https://docs.aside.com/help/security) |
| Follow-ups | Queue waits for the current run. Steer injects a message into the active run. | official, [Run tasks](https://docs.aside.com/help/tasks) |
| Ultrabrowse | Reasoning mode for citation-heavy research and multi-site comparison. Free plan prompts to upgrade to Pro. | official, [Ultrabrowse](https://docs.aside.com/help/ultrabrowse) and [Pricing](https://aside.com/pricing) |
| Human approval | Sensitive actions such as payments, posts, and messages wait for confirmation. | official, home and password-manager help |
| Computer Use | Agent can work across desktop apps on Mac and Windows. Settings > Agents > Computer Use. Changelog says Max subscribers and experimental accounts. | changelog, 2026-10-23 |
| Channels | Slack, Discord, Telegram remote control. Pro pricing lists Channels. | official pricing + changelog |
| Cloud handoff | Listed on the Pro plan. Mechanism is unconfirmed from public pages read in this pass. | official marketing, mechanism unconfirmed |
| Routines | Unlimited on Pro. Free plan limits exist. | official, [Pricing](https://aside.com/pricing) |
| Projects | Named workspace folder, Project `AGENTS.md`, archive without deleting tasks. | changelog |
| Skills | Custom skills, `aside skills install` into Codex, Claude Code, Cursor, or OpenCode. | changelog + [Developers](https://docs.aside.com/help/developers) |

## Memory and vault

| Feature | What the docs say | Evidence |
| --- | --- | --- |
| History as memory | Browsing history becomes task context. Memory stays on device in the marketing claim. | official, [Memory marketing](https://aside.com/features/memory) |
| Dreaming | After a task, Aside extracts people, companies, and decisions into markdown files such as `episodic/`. | official marketing page, including a visible extraction prompt |
| Site-specific memory | Remembers a path that worked when the agent got stuck on a site. | official marketing |
| Retention | Never forget, 30 days, or 90 days. User can review and edit. | official, [Manage memory](https://docs.aside.com/help/memory) |
| Local embeddings | Self-organizing memory powered by local embedding models. | official, [SOTA blog](https://aside.com/blog/how-we-built-the-sota-browser-agent-that-outperforms-fable) |
| Vault autofill | Agent can trigger login. Raw password is not given to the model. | official, [Password manager help](https://docs.aside.com/help/password-manager) |
| Vault policy | Always allow, While unlocked, Never. No vault use in incognito. | official help |
| Passkey, FIDO2, TOTP | Supported where the site asks. Agent can fill TOTP without seeing the secret, per changelog. | official help + changelog |
| Unlock | Touch ID on macOS. Windows Hello on Windows. | official help |
| Hardware-backed encryption | Marketing says Secure Enclave and post-quantum encryption. Secure Enclave is an Apple name. Windows equivalent is unconfirmed. | official marketing, Windows mapping unconfirmed |
| Import vaults | 1Password, Apple Passwords, Bitwarden, Dashlane, LastPass, Chrome. | official marketing |

## Developer surface

| Feature | What the docs say | Evidence |
| --- | --- | --- |
| CLI | `aside "task"`, `--session`, `aside account *`, `aside exec`. macOS install via `curl …/install.sh`. Windows install path exists as a docs tab. | official, [Developers](https://docs.aside.com/help/developers) |
| MCP | `aside mcp` with `mcp.json` command `aside` args `["mcp"]`. | official |
| REPL | `aside repl "const p = await openTab('https://example.com')"`. | official |
| BYO models | Home page says ChatGPT or Claude subscriptions, or an API key. Changelog adds Kimi Code, Qwen, Gemini Flash, Ollama, LM Studio. | official + changelog |

Exact MCP tool names exported by `aside mcp` are unconfirmed. This session did not run the Aside CLI.

## Pricing claims

Home and pricing pages list Free and Pro. Pro is marketed at $20 per month with 3x Free usage, Ultrabrowse, unlimited routines, Channels, and cloud handoff. Official, [Pricing](https://aside.com/pricing). Seat, team vault, and shared-profile bullets appear on the same page. Metering numbers are unconfirmed.

Benchmark claims on the home and browser-agent pages are Aside's own published scores (Online-Mind2Web, BU-Bench-V1, Odysseys). Official marketing. This investigation did not rerun those benches.

## Not confirmed in this pass

- Installed-app screenshot of Ask AI, Agent Tabs, Vault, or Computer Use.
- Whether Windows uses Secure Enclave-class hardware wrapping or only Windows Hello plus software encryption.
- Full skill catalog shipped in the app.
- Whether Cloud handoff runs the agent off-device.
- Bot-detection modifications as they exist in the current Windows build.
- Any IRIS-relevant private API that is not on the public site.
