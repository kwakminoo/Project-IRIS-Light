# Candidate B stages

A is already on this branch. B adds a view-model boundary. Apply and live Shell approve stay out.

Shared files serialize. One stage finishes and its check is green before the next stage starts. Each stage is a fresh agent.

## Stage 1. Models

Create `iris/ui/chat/card_models.py`.

Own `FenceInfo`, `parse_fence_info`, `format_fence_info`, `CodeCardModel`, `ShellCardModel`, `to_code_card`, `to_shell_card`.

`CodeCardModel` holds body text, lang id, header primary, header secondary, copy payload, and open path. It does not hold HTML.

`ShellCardModel` holds title, command, output, status kind (`ok` or `error`), status label (`성공` or `실패`), block id, collapsed, and whether to show command copy. Copy payload is the command text.

`to_code_card` reads `FencedCodeBlock`. If `path` is empty, it still parses `language` with `parse_fence_info` so `python:iris/foo.py` yields a path.

Do not import `chat_blocks` at module level. Anchor strings stay out of this module.

Move the parse functions out of `chat_blocks.py`. Update imports. Do not leave a second parser.

Check: `python -m iris.ui.chat._check_card_models` and `python -m iris.ui.chat._check_chat_blocks`.

## Stage 2. HTML

Create `iris/ui/chat/card_html.py`.

`code_card_to_html(CodeCardModel)` and `shell_card_to_html(ShellCardModel)` are the only painters.

Match today's card text. Path basename is primary. Language is muted secondary. `열기` uses `iris-file://`. `복사` copies code. Shell shows `성공` or `실패` and `명령 복사`.

Import anchors from `chat_blocks` inside functions if needed so imports do not cycle.

Check: `python -m iris.ui.chat._check_card_html`.

## Stage 3. One door

`fenced_code_to_html` and `tool_shell_to_html` become facades.

`wire -> to_*_card -> *_card_to_html`.

Delete the old HTML bodies in `chat_blocks.py`. Product code does not call `card_html` except those facades and tests.

Check: `python -m iris.ui.chat._check_chat_blocks` and `python -m iris.ui._check_chat_block_parser`.

## Stage 4. Thin wire

Remove `path`, `start_line`, and `end_line` from `FencedCodeBlock` and `CodeSegment`.

The fence info string lives in `language` until `to_code_card` parses it.

Streaming rebuild uses the raw info string, not deleted fields.

Headers for `python:path` still show basename, `열기`, and `복사`.

Check: the three commands above.
