# Implementation units

1. Types + ChatTranscript test. Check: unittest green.
2. Engine stub (`ensure_ready` / `run_turn` / `shutdown` signatures) + shared singleton test. Check: import and idempotent shutdown with no child.
3. Sidecar protocol parse + stdout-reserved host script that refuses GuiPython. Check: parse unknown event → PROTOCOL; host exits 2 under IRIS python.
4. Install into EngineHome (clone bypass, pin SHA, probe EnginePython). Check: probe fail is WRONG_PYTHON, does not spawn.
5. Wire health + chat workers + closeEvent. Delete default `ensure_hermes_gateway_running` / `HermesClient(...)` callers in the same change. Check: workers construct without URL/key; close calls shutdown.
6. HUD flags + DANGEROUS_ACTIONS boot assert + IRIS_ENGINE_TOOLS catalog check. Check: missing confirm_required fails the assert.
7. Live IRIS: ready without manual gateway, chat, YouTube tool, cancel, quit leaves no :8642.

Do not start unit N+1 until unit N is green.
