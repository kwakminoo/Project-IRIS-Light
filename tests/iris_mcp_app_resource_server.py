"""Tiny stdio MCP resources/read fixture for Phase 4d checks."""

from __future__ import annotations

import json
import sys


HTML = "<!doctype html><html><body>stdio mcp app</body></html>"


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}},
                    "serverInfo": {"name": "fixture-app", "version": "1"},
                },
            }
        )
    elif method == "resources/read":
        uri = str((message.get("params") or {}).get("uri") or "")
        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/html;profile=mcp-app",
                            "text": HTML,
                        }
                    ]
                },
            }
        )
