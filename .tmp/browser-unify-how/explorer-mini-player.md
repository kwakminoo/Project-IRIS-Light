# Explorer 4 — YouTube mini player UX

See parent chat explorer [YouTube mini player](55680b4c-77ea-4f1d-a699-9266f1477648).

Implemented: reparent one view, drag on title bar, expand, close (parks view in hidden panel, no pause), auto-mini on IDE stack leave for watch URLs, browser.mini_player command, _check_mini_player reparent+driver id.

Missing: resize (setFixedSize), chat-panel PIP, geometry clamp on drag, follow parent move, auto-mini after navigate, auto-mini when leaving workspace page.

Tests do not cover drag/resize/clamp/PIP/media.playing across switch.
