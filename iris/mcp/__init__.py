"""Iris MCP adapters (stdio bridges for Hermes).

Agent-readable:
- Owns: Hermes ↔ IRIS stdio MCP bridge surface (`iris-control` tools).
- Does not: LLM inference, tool execution inside Hermes, or UI widgets.
- Talks to: Hermes MCP config (`mcp_servers.iris-control`), Control Surface HTTP.
- Extend via: new MCP server process or `integrations/hermes-skills/` (prefer core diff=0).
"""
