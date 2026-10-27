# About Aside's published architecture

This file is an explanation of how Aside says it is built. It is not a decompilation. Engine internals that only exist in the closed binary stay `unconfirmed`.

Primary source: Jun Kim, [How we built a browser agent that outperforms Fable](https://aside.com/blog/how-we-built-the-sota-browser-agent-that-outperforms-fable), 2026-06-25. Supporting sources are the help center, the native changelog's Chromium version line, and the developer docs.

## Why Aside exists as a whole browser

Aside's bet is that an agent that "uses websites" needs a real logged-in browser, not a headless bot and not a Chrome extension that steals focus. The blog lists four product constraints that then force engine work:

1. Use the user's existing accounts. No per-site API integrations.
2. Remember work with local embeddings.
3. Autofill credentials without showing secrets to the model.
4. Look like a real browser so sites do not treat the agent as a bot.

Open-sourcing the browser is explicitly refused in that FAQ. A separate "browser framework" is only a maybe.

## Engine

The native changelog publishes Chromium version bumps, for example `153.0.8010.53` → `154.0.8037.100`. Changelog, [Native changelog](https://docs.aside.com/changelog/native). Combined with the blog's "we patched Chromium's Blink engine", the supported conclusion is that Aside is a Chromium fork, not a Qt WebEngine embed and not a documented Electron shell.

Electron is unconfirmed. No official page read in this pass names Electron. The Chrome Web Store link and extension-copy-on-profile flows in the changelog fit a Chromium browser with extensions.

Blog-stated Blink patches:

- Agent-opened tabs do not take focus or open interrupting popups.
- Internals changed to reduce bot detection, using the same technique family as Browserbase and Browser Use. The exact patch list is unconfirmed.
- Background agent tabs render at a locked 1440×900 viewport.

Those patches are official claims about their Chromium tree. They cannot be verified here because Aside is not installed.

## Agent harness

Aside describes itself as a coding agent inside a browser. The blog says the core tools are a JS REPL and `bash`, not a catalog of `browser.click` style tools. It names Hermes (and OpenClaw) as the opposite design, dedicated browser-control toolsets.

Foundation named in the blog: `pi-mono/core`. Compaction, skills, hooks, sandbox, REPL, bash, and browser automation were built on top.

Design rules they state:

- Follow the model's training data. Playwright JS is the browser language they believe models already know. The prompt does not teach Playwright. It says Playwright is available.
- Keep the system prompt small. They claim about 10K tokens including tool definitions.
- Do not put raw CDP or raw DOM in the model context. CDP is called a bad agent interface because models are not trained on it and it wastes tokens.

This is Aside's published opinion. It is useful as a contrast with IRIS, which already owns a dedicated toolset. It is not an instruction to throw that toolset away. See `05_IMPLEMENTATION_PLAN.md`.

## Asidewright

Playwright as a test runner is, in their words, too heavy for an agent. Asidewright is their replacement:

- Interface claimed 100% identical to Playwright.
- Each API is a thin wrapper over CDP. No injected scripts, in their claim.
- Token use claimed up to 80% below agent-browser.
- Asynchronous steering events: popup opened, download started, tab closed.

Page reading uses a trimmed accessibility tree. They drop intermediate nodes and add focus, iframe id, and clickable state. They claim a 70% smaller snapshot than agent-browser on `aside.com/sota`.

When the DOM is not enough, Asidewright exposes a Computer Use / screenshot coordinate fallback. Changelog later adds desktop Computer Use for other apps, which is a different surface from in-page CUA.

Network workaround: if the visible path is blocked, the agent may capture requests, recover the site's internal API, and replay a same-looking request. Official blog. That is an agent strategy, not a documented IRIS-safe default.

## Process and permissions

Help center permission model:

- Agent-level rules under Settings > Agents. Allow, Ask, Deny on tool groups. Deny wins.
- Session modes on each task: Read only, Guard, Full access. Guard is the default.
- Sandbox is described as OS-level isolation for commands. The isolation technology (containers, job objects, Seatbelt) is unconfirmed.
- File access is folder-scoped. Full access still does not expose saved password values.

Vault path, official help: task hits a login page → Aside checks URL and access policy → autofill payload is built without giving the password to the model. MFA, passkeys, CAPTCHA still need a person.

Memory path, official marketing plus help: history and task transcripts are extracted into on-device markdown. A "dreaming" subagent writes episodic files. Moss.dev describes a local retrieval layer at 80,000+ devices. That Moss article is `third-party`. Treat device counts as unverified.

## Developer loop

CLI starts the same browser agent from a terminal. MCP (`aside mcp`) exposes that agent to another coding tool. REPL is for deterministic Playwright-shaped steps. External MCP or CLI tabs land in Agent Tabs. Official developers page and native changelog.

## What this architecture is not

It is not a headless Playwright job that then paints a fake browser. The blog's whole point is that the agent lives in the user's real browser.

It is not an IRIS-style Qt panel driven by named `browser.*` tools. Aside's public design argues against that exact shape.

It is not open source. You cannot read Asidewright or the Blink patches from GitHub. Public code under [at-inc](https://github.com/at-inc) is benchmarks and related repos, not the browser.

The homepage says tasks, memory, and data stay on the device and nothing is shared with LLM providers. Official marketing, [home](https://aside.com/). The privacy policy, last updated 2026-06-23, says Aside is local-first and that hosted model providers receive model-visible context. That context can include prompts, instructions, tool results, selected snapshots, selected screenshots, selected files, and assistant responses. Official, [Privacy policy](https://aside.com/policy/privacy) section 4. Optional encrypted Chromium sync (bookmarks, history, cookies, device info, Nigori) and vault sync leave the device when enabled. Analytics, when on, go to PostHog. Support uses Intercom. Billing uses Stripe.

Native changelog and components changelog are two release trains. Chromium version bumps live on the native train. Agent, vault, and local-service notes live on the components train.

1Password docs say 1Password does not recognize Aside as a Chromium-based browser, so the native messaging host must be copied. Official troubleshooting. That is a host-manifest gap, not a denial that the engine is Chromium.

## Unconfirmed internals

- Language of the native shell (C++, Swift, WinUI, or something else).
- Whether the REPL process is in the renderer, a utility process, or a helper named in the changelog as Aside Helper.
- How local embeddings are stored (SQLite, custom files, Moss).
- Current Chromium major on the Windows installer as of this writing. Changelog cited 154.x in one native entry. Live installer version was not downloaded.
- Precise bot-detection patch list.
- Electron. No official page read in this pass names it.
- Exact `aside mcp` tool names.
