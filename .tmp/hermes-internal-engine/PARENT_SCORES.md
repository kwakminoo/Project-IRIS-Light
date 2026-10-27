# Parent scores (before cross-judge)

Scale: 0 miss, 1 partial, 2 meet.

| Criterion | C1 sidecar Engine | C2 hosted supervisor | Note |
|---|---|---|---|
| 1 Never install/start/attach | 2 | 2 | Both drop default `:8642`. |
| 2 Keep chat/browser/tools/SQLite seams | 2 | 1 | C2 hosted path drops MCP and uses IPC `tool_call` → `call_registered`. Same registry, different transport. |
| 3 Reuse Hermes loop | 2 | 2 | Both `AIAgent.run_conversation`. |
| 4 Faults stay out of Qt | 2 | 2 | C2 adds an import lint. Same process wall. |
| 5 Small public surface | 2 | 1 | C2 `stream_turn` takes `ChatAttempt`. `attach_compat` is a second entry. |
| 6 Compat without a second chat path | 2 | 2 | Both hide HTTP in `_compat`. |

Convergence: both rejected in-process import and a polished gateway as the product.

Graft if C1 is base: C2 `EngineHome`≠`HermesHome`, `DANGEROUS_ACTIONS` boot assert, import lint, `IRIS_ENGINE_TOOLS` single list, `EnginePhase` READY/COMPAT exclusive.

Graft if C2 is base: C1 `run_turn` calls `ensure_ready`, `EngineSource` union instead of `attach_compat`, reuse `HermesInferenceTarget`, keep MCP on hosted path so tool transport does not change in the first wave.
