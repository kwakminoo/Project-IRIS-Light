# PROVENANCE — vendor/iris-agent-core

## Purpose / 목적

Iris Agent **owned frozen tree** (Phase ACO-P2).  
Known-good upstream checkout + Iris baseline overlays baked into source.  
P3 renames the distribution to `iris-agent-core`; this tree is the freeze input
(pyproject `name` may already read `iris-agent-core`).

이 트리는 제품이 소유하는 동결 에이전트 코어다. 설치 경로
`~/.iris-light/agent/hermes-agent`(Reference Engine)는 건드리지 않는다.

## Upstream

| Field | Value |
|-------|-------|
| URL | https://github.com/NousResearch/hermes-agent.git |
| Pin SHA | `a382af23f4c067d23463b5781958684c2cda82bc` |
| License | **MIT** (Nous Research) — see `LICENSE` in this directory |
| Copied from | `%USERPROFILE%\.iris-light\agent\hermes-agent` at that SHA |
| Product pin | `vendor/iris-agent-runtime/PIN` (same SHA) |

## Excluded from copy

`venv/`, `.git/`, `**/__pycache__/`, `*.pyc`, `*.egg-info/`, `.pytest_cache/`,
`node_modules/`, `website/`, `*.whl` caches.

## Applied Iris changes (baked)

Via workspace venv:

```text
apply_iris_agent_baseline_overlays(Path('vendor/iris-agent-core'))
apply_absorbed_toolsets_overlay(Path('vendor/iris-agent-core'))  # not inlined in baseline
```

Recorded messages (ACO-P2 final bake):

- ollama options guard: present in baseline
- hermes dead-check: pattern unknown — ok at pin (upstream polarity fix)
- tool_choice.py installed (+ chat/turn/agent_init/side_question/config_defaults wiring)
- package identity: no hermes-agent markers — skipped (`name` already `iris-agent-core`)
- cli rename: `iris_agent_cli` real; `hermes_cli` → reverse shim
- cli shim: superseded by F3 rename
- absorbed_toolsets overlay present

## Entry points (smoke)

| Role | Path |
|------|------|
| AIAgent | `run_agent.py` (`class AIAgent` ~L214) |
| CLI package | `iris_agent_cli/` (post-rename); `hermes_cli/` reverse shim |

## Tracking note

Upstream `.gitattributes` kept (LF normalization). `website/` excluded to bound
repo size. Full tree is still large (~apps + tests); track as a single vendor
directory.

## Verification note

`PYTHONPATH=vendor/iris-agent-core`: `iris_agent_cli` / `hermes_cli` import OK;
`class AIAgent` present in `run_agent.py` (AST). Full `from run_agent import
AIAgent` needs agent deps (e.g. `ruamel`). Reference install untouched at
`~/.iris-light/agent/hermes-agent` @ `a382af23…`.
