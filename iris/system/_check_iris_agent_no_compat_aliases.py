"""Public runtime symbols use Iris Agent names only."""

from __future__ import annotations


def main() -> None:
    from iris.infrastructure import iris_agent_client as client
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
    }
    leftovers = [
        f"{module.__name__}.{name}"
        for module, names in banned.items()
        for name in names
        if hasattr(module, name)
    ]
    assert not leftovers, "compat aliases remain: " + ", ".join(leftovers)
    print("iris_agent_no_compat_aliases ok")


if __name__ == "__main__":
    main()
