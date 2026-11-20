---
name: iris-past-chats
description: >
  Search prior Iris chat conversations when the user asks about earlier talk.
  Use when: 이전 대화, 저번에, 예전에, 지난번, 그때, remember what we did,
  prior chat, past conversation, what did we decide last time.
---

# Iris past chats

## Tools

Prefer Iris Agent SpeakTools (no MCP Control HTTP):

- `chat.search_past` (provider name may appear as `chat_search_past`)
  - Required: `query` — topic words from the user's ask
  - Optional: `limit` — 1..3 (default 3)

This is **not** `wiki.search`. Wiki notes are saved vault files. Past chats are
other conversation transcripts in Iris History.

## When

- User asks what was said / decided / fixed in a **prior** chat.
- Phrases like 저번 / 이전 대화 / 예전에 / 지난번 / remember what we did.
- Same-chat follow-ups ("이어서", "계속", "방금 그거") need **no** tool — the
  current transcript already has that context.

## Steps

1. Call `chat.search_past` with a short `query` that names the topic.
2. Read `hits` / `prompt_block` / `sources_note` / `count` from the ok result.
3. Answer from those hits. Say you used a prior chat when you rely on them.
4. If `count` is 0 or settings disabled (`message` present), say nothing useful
   was found — do not invent a prior chat.

## Rules

- Never invent past chats without a successful tool ok that has hits.
- Do not treat `wiki.search` excerpts as chat History.
- Do not call this tool on every turn. Only when the user asks about prior chats.
- Current conversation is already excluded by the tool.
