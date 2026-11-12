"""Adapter self-check: list_model_entries + ApiProvider.model_meta round-trip."""

from __future__ import annotations

import json

from iris.infrastructure.model_roster import RosterEntry
from iris.infrastructure.openai_compat_client import _model_entries, _model_ids
from iris.storage.api_providers import (
    ApiProvider,
    _from_dict,
    apply_roster_to_provider,
    roster_from_provider,
    sanitize_model_meta,
)


def main() -> None:
    payload = {
        "data": [
            {
                "id": "brand/free-chat:free",
                "description": "Official free tier blurb",
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"modality": "text->text"},
            },
            {
                "id": "brand/embed",
                "summary": "Embedding only",
                "type": "embedding",
            },
            {"name": "missing-id"},
        ]
    }
    entries = _model_entries(payload)
    assert [e["id"] for e in entries] == ["brand/free-chat:free", "brand/embed"]
    assert entries[0]["description"] == "Official free tier blurb"
    assert entries[0]["pricing"] == {"prompt": "0", "completion": "0"}
    assert entries[1]["summary"] == "Embedding only"
    assert _model_ids(payload) == ["brand/free-chat:free", "brand/embed"]

    provider = ApiProvider(
        name="Brand",
        base_url="https://example.test/v1",
        models=["gone", "kept", "brand/free-chat:free"],
        model_states={"gone": "unavailable", "kept": "ok"},
        tool_support={"kept": "yes"},
    )
    assert provider.model_meta == {}

    roster = [
        RosterEntry(
            model_id="brand/free-chat:free",
            description="Official free tier blurb",
            price_class="free",
            modality="chat",
            availability="ok",
            tool_support="unknown",
            listing_seen_at="2026-11-12T01:00:00Z",
        ),
        RosterEntry(
            model_id="kept",
            description="",
            price_class="unknown",
            modality="unknown",
            availability="ok",
            tool_support="yes",
            price_refetch_done=True,
        ),
        RosterEntry(
            model_id="gone",
            description="Was listed",
            price_class="paid",
            modality="chat",
            availability="unavailable",
            tool_support="no",
            retired=True,
            retired_at="2026-11-12T00:00:00Z",
            retire_evidence="listing-missing",
        ),
        RosterEntry(
            model_id="brand/embed",
            description="Embedding only",
            price_class="unknown",
            modality="embedding",
            availability="unverified",
        ),
    ]
    apply_roster_to_provider(provider, roster)
    assert provider.models == ["gone", "kept", "brand/free-chat:free", "brand/embed"]
    assert "gone" in provider.models
    assert provider.model_states["gone"] == "unavailable"
    assert provider.model_meta["gone"]["retired"] is True
    assert provider.model_meta["brand/free-chat:free"]["description"] == (
        "Official free tier blurb"
    )

    # Partial apply must not drop unavailable/retired ids from models[]
    apply_roster_to_provider(
        provider,
        [
            RosterEntry(
                model_id="kept",
                description="",
                price_class="free",
                modality="chat",
                availability="ok",
                tool_support="yes",
            )
        ],
    )
    assert provider.models == ["gone", "kept", "brand/free-chat:free", "brand/embed"]
    assert provider.model_meta["gone"]["retired"] is True

    # JSON serialize / load round-trip (preference shape)
    row = {
        key: value
        for key, value in vars(provider).items()
        if key != "api_key"
    }
    loaded = _from_dict(json.loads(json.dumps(row)))
    back = roster_from_provider(loaded)
    by_id = {e.model_id: e for e in back}
    assert loaded.models == ["gone", "kept", "brand/free-chat:free", "brand/embed"]
    assert by_id["gone"].retired is True
    assert by_id["gone"].retire_evidence == "listing-missing"
    assert by_id["brand/free-chat:free"].description == "Official free tier blurb"
    assert by_id["brand/free-chat:free"].price_class == "free"
    assert by_id["brand/embed"].modality == "embedding"
    assert by_id["kept"].price_class == "free"

    legacy = sanitize_model_meta(None)
    assert legacy == {}
    assert sanitize_model_meta({"x": "bad"})["x"]["price_class"] == "unknown"

    print("model_roster_persist self-check ok")


if __name__ == "__main__":
    main()
