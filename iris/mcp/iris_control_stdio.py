"""Tombstone — iris-control MCP is removed from the product path.

Product speak uses SpeakTools only. This module must not run as an MCP server.
TOOLS stays empty so boot checks can prove MCP is not the speak catalog.
"""

from __future__ import annotations

import sys

TOOLS: list = []


def main() -> int:
    sys.stderr.write(
        "iris-control MCP removed; product path uses SpeakTools only.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
