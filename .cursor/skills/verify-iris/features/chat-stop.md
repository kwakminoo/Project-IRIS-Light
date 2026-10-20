# Chat stop

Chat stop proves the stop / cancel control for an in-flight assistant turn stays wired so the user can halt generation without killing Iris.

## Sub-features

- `stop-button` asserts the stop control exists and connects to cancel paths.
- `turn-cancel` covers conversation switch / cancel contracts used by the chat host.

## How to get to it (user POV)

- Send a chat message, then click Stop (or the equivalent control) while the assistant is still generating.

## Driving it with verify-iris

Preconditions:

- `doctor.py` reports `ok: true`.

- **Run prove.** `.\.venv\Scripts\python.exe .cursor\skills\verify-iris\scripts\prove_feature.py --feature chat-stop`
- **Observe.** Exit code `0`. Evidence under `.../chat-stop/report.json`.
- **Related headless.** For turn follow-up slot safety after wiki/chat finish: `.\.venv\Scripts\python.exe -m iris.ui._check_turn_followup` (not yet a prove_feature id; add when used often).

## Gotchas

- Slot exceptions during send/finish abort the whole process (`0xC0000409`). A check failure here is higher severity than a styling miss.
- Live LLM stop requires a running model path. Headless prove covers wiring, not network latency.
