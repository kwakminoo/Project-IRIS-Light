# Arena rubric

Artifact: design package (USAGE, DESIGN types/signatures, RATIONALE, REJECTED).

1. User never installs, starts, or attaches Hermes. IRIS-only launch reaches a ready agent.
2. Chat UI, BrowserSession, YouTube/mini-player, Control Surface, SQLite history stay on their current seams.
3. Hermes agent loop is reused, not rewritten.
4. Agent faults stay out of the Qt process (`0xC0000409` cannot come from the loop).
5. Public surface is small. Callers do not coordinate install, port, key, and spawn.
6. External Hermes remains a compatibility mode without a second chat path.
