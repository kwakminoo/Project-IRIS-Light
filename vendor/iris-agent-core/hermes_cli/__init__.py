"""Iris CLI reverse shim — re-exports iris_agent_cli (F3 install overlay)."""
from iris_agent_cli import *  # noqa: F401, F403
import iris_agent_cli as _iris_agent_cli

# Submodule imports (hermes_cli._early_recovery) resolve into iris_agent_cli.
__path__ = list(_iris_agent_cli.__path__)
