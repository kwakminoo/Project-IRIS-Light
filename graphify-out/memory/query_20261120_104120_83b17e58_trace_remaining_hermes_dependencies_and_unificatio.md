---
type: "query"
date: "2026-11-20T10:41:20.159392+00:00"
question: "Trace remaining Hermes dependencies and unification work in IRIS"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Engine", "Hermes", "runtime", "Gateway", "iris"]
---

# Q: Trace remaining Hermes dependencies and unification work in IRIS

## Answer

Expanded from original query via graph vocab: [iris, hermes, agent, runtime, gateway, sidecar, toolsets, compat, legacy, client, engine, control]. Current product path is InternalSidecar and IrisAgent classes; inventory checks show 0 logic hermes modules, 0 ExternalGateway product files, 0 legacy hermes-home files, and 17 thin re-export shims. Remaining real coupling is the pinned upstream runtime package and process contract: hermes_cli imports, HERMES_HOME, run_agent.AIAgent, checkout layout, and overlay patching. Remaining cleanup is IRIS_HERMES env persistence, hermes-prefixed function/property aliases, 17 shim files, tests/docs, and stale README architecture. Live absorbed-toolsets bug was fixed and a local gemma4:12b turn completed with OK.

## Outcome

- Signal: useful

## Source Nodes

- Engine
- Hermes
- runtime
- Gateway
- iris