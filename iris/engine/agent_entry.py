"""Iris-owned boundary to the Agent Core conversation loop.

Product code imports AIAgent only through this module (or IRIS_ENGINE_AGENT_MODULE).
The implementation currently comes from the installed/frozen Agent Core ``run_agent``
(Hermes-derived, MIT). Do not import Hermes internals from UI or SpeakTools paths.
"""

from run_agent import AIAgent

__all__ = ["AIAgent"]
