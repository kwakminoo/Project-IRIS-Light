# Chat scroll validation

Validated on 2026-10-06 with Qt offscreen on Windows, using the main layout and
`IdeCompanionPage.mount()` with the actual cyberspace stylesheet.

Both screens reuse the same `ChatPanel` and `ChatLogTextEdit`. The response-start
anchor has been removed: only users at the bottom follow new output. Wheel and
scrollbar actions update that choice before any subsequent document changes.
Reading earlier messages preserves the scroll value through streaming, typed
output, final Markdown rendering, and additional messages. Clearing a session
restores bottom following.

The viewport shares a 24 logical pixel alpha fade at the top. It ramps in during
the first 24 pixels of scrolling and is disabled at scroll position zero. It
changes the actual message pixels rather than painting a background overlay.
The document has 28 pixels of top padding; scrollbars remain outside the effect.
A local 8 pixel scrollbar overrides the global theme's hidden scrollbar sizing.

Validation:

- `tests.test_chat_scroll`: identical wheel distance in main and IDE layouts;
  actual thumb press/move/release; held position during typing and streaming;
  scrolling up during an active stream; returning to the bottom; continuous
  following through a long response and its final render; session reset.
- Rendered images inspected for both layouts. Pixel assertions confirm the fade
  reduces top text alpha and does not change document geometry.
- `tests.test_chat_scroll`, `tests.test_chat_typography`, and
  `tests.test_chat_rendering_pipeline`: 13 tests passed.
- `python -m iris.ui._check_chat_typing_anchor`: passed; this legacy entry point
  now runs the shared scroll regression scenarios.

Images are written to `.iris_light_test_tmp/chat-scroll-main.png` and
`.iris_light_test_tmp/chat-scroll-ide.png`. The tests explicitly register Windows
fonts because the offscreen plugin does not discover them automatically.
The checked-in virtual environment's base Python executable was absent, so the
tests used a temporary project-local Python 3.12 runtime and existing dependencies.

These are Qt event and rendered-widget comparisons, not a manual session in the
running IDE. The separate legacy `_check_chat_resize` check fails its hardcoded
`15px` HTML assertion under this runtime's default 13px code font; its earlier
layout and orb fade assertions pass. No change was made to that unrelated check.
