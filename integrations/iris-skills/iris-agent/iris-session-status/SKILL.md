---
name: iris-session-status
description: >
  Summarize current Iris Light session: companion mode, workspace, IDE, project_root,
  model, agent online, email accounts. Use when asked: 지금 상태, 세션 요약,
  Iris status, what's open, companion 켜져 있어?
---

# Iris session status

## Steps

1. Prefer native `iris.tools.catalog` when checking which Iris tools exist.
   For live UI state call native `iris.session.get_state` (alias `get_state`) —
   product speak path, no MCP Control HTTP. If the result is `requires_iris_ui`,
   tell the user to ask from Iris chat (or click) so Qt MainWindow can answer.
2. Reply in a short bullet list: ui_mode, workspace_mode, preferred_ide, project_root, model, agent online.
   Map any legacy `*_online` agent flag to the label "agent online" for the user.
3. Do not invent fields that are missing from the tool result.
