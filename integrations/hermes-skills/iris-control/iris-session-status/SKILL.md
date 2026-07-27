---
name: iris-session-status
description: >
  Summarize current Iris Light session: companion mode, workspace, IDE, project_root,
  model, Hermes online, email accounts. Use when asked: 지금 상태, 세션 요약,
  Iris status, what's open, companion 켜져 있어?
---

# Iris session status

## Steps

1. Call `iris_get_state` (and optionally `iris_get_catalog` only if planning further actions).
2. Reply in a short bullet list: ui_mode, workspace_mode, preferred_ide, project_root, model, hermes_online.
3. Do not invent fields that are missing from the tool result.
