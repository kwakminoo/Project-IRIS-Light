"""Public runtime symbols use Iris Agent names only."""

from __future__ import annotations


def main() -> None:
    from iris.runtime import backend_route
    from iris.storage.failover_prefs import FallbackEntry
    from iris.infrastructure import iris_agent_client as client
    from iris.system import iris_agent_update as update_mod
    from iris.ui.workers import backend_call
    from iris.ui.workers import iris_agent_update_worker as update_worker
    from iris.ui.workers import iris_agent_workers as workers

    banned = {
        client: (
            "HermesClient",
            "HermesInferenceTarget",
            "normalize_hermes_openai_base_url",
            "resolve_hermes_inference",
        ),
        workers: (
            "HermesHealthWorker",
            "HermesChatWorker",
            "HermesControlSyncWorker",
            "HermesModelSyncWorker",
        ),
        update_worker: ("HermesUpdateCheckWorker", "HermesUpdateApplyWorker"),
        update_mod: ("HermesUpdateStatus",),
        backend_call: ("BACKEND_HERMES", "_hermes"),
        backend_route: ("LEGACY_HERMES_BACKEND",),
    }
    leftovers = [
        f"{module.__name__}.{name}"
        for module, names in banned.items()
        for name in names
        if hasattr(module, name)
    ]
    assert not leftovers, "compat aliases remain: " + ", ".join(leftovers)
    assert backend_call._AGENT_BACKENDS == frozenset({"agent"})
    assert backend_route.is_agent_backend("agent") is True
    assert backend_route.is_agent_backend("hermes") is False
    assert FallbackEntry(model="m", backend="hermes").backend != "agent"
    print("iris_agent_no_compat_aliases ok")


if __name__ == "__main__":
    main()
