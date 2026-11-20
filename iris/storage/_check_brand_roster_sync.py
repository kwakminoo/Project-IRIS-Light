"""Brand listing sync helper: retire/confirm_missing/price refetch/410 without network."""

from __future__ import annotations

from iris.infrastructure.model_roster import DisplayTier, apply_probe, display_tier
from iris.infrastructure.openai_compat_client import ProbeResult
from iris.storage.api_providers import (
    ApiProvider,
    is_nvidia_integrate_base,
    retire_provider_on_http,
    roster_from_provider,
    sync_provider_listing,
)


def main() -> None:
    bare = ProbeResult("error", detail="x")
    assert bare.model_entries == []
    listed = ProbeResult("ok", models=["a"], model_entries=[{"id": "a", "pricing": {}}])
    assert listed.models == ["a"]
    assert listed.model_entries[0]["id"] == "a"

    provider = ApiProvider(
        id="brand1",
        name="Brand",
        base_url="https://example.test/v1",
        models=["keep", "gone"],
        model_states={"keep": "ok", "gone": "ok"},
    )
    full = sync_provider_listing(
        provider,
        [
            {"id": "keep", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "new", "pricing": {"prompt": "0.001", "completion": "0.002"}},
        ],
        confirm_missing=True,
        now_iso="2026-11-12T10:00:00+09:00",
    )
    assert "gone" in provider.models
    assert "new" in provider.models
    by_id = {e.model_id: e for e in full.entries}
    assert by_id["gone"].retired is True
    assert by_id["gone"].availability == "unavailable"
    assert "gone" in full.retired_ids
    assert by_id["keep"].retired is False
    assert by_id["new"].price_class == "paid"

    provider2 = ApiProvider(
        id="brand2",
        name="Partial",
        models=["keep", "gone"],
        model_states={"keep": "ok", "gone": "ok"},
    )
    partial = sync_provider_listing(
        provider2,
        [{"id": "keep"}],
        confirm_missing=False,
        now_iso="2026-11-12T10:01:00+09:00",
    )
    gone2 = next(e for e in partial.entries if e.model_id == "gone")
    assert gone2.retired is False
    assert partial.retired_ids == ()

    empty = sync_provider_listing(
        provider2,
        [],
        confirm_missing=False,
        now_iso="2026-11-12T10:02:00+09:00",
    )
    assert not any(e.retired for e in empty.entries)

    provider3 = ApiProvider(id="b3", name="EOL", models=["eol"], model_states={"eol": "ok"})
    retire_provider_on_http(
        provider3,
        "eol",
        status=410,
        evidence="http-410",
        now_iso="2026-11-12T10:03:00+09:00",
    )
    eol = roster_from_provider(provider3)[0]
    assert eol.retired is True
    assert eol.availability == "unavailable"
    assert provider3.model_states["eol"] == "unavailable"
    probed = apply_probe(eol, availability="ok", tool_support="yes")
    assert probed.retired is True

    revived = sync_provider_listing(
        provider3,
        [{"id": "eol", "pricing": {"prompt": "0", "completion": "0"}}],
        confirm_missing=True,
        now_iso="2026-11-12T10:04:00+09:00",
    )
    back = next(e for e in revived.entries if e.model_id == "eol")
    assert back.retired is False
    assert provider3.model_meta["eol"]["retired"] is False

    provider4 = ApiProvider(id="b4", name="Price", models=["u1"])
    calls: list[int] = []

    def _refetch():
        calls.append(1)
        return [{"id": "u1", "description": "still unknown"}]

    priced = sync_provider_listing(
        provider4,
        [{"id": "u1"}],
        confirm_missing=True,
        refetch_entries=_refetch,
        now_iso="2026-11-12T10:05:00+09:00",
    )
    assert calls == [1]
    u1 = next(e for e in priced.entries if e.model_id == "u1")
    assert u1.price_class == "unknown"
    assert u1.price_refetch_done is True
    assert priced.needs_price_refetch is False
    assert provider4.model_meta["u1"]["price_refetch_done"] is True

    assert is_nvidia_integrate_base("https://integrate.api.nvidia.com/v1")
    assert is_nvidia_integrate_base("https://INTEGRATE.API.NVIDIA.COM/v1/")
    assert not is_nvidia_integrate_base("https://openrouter.ai/api/v1")
    assert not is_nvidia_integrate_base("https://example.test/v1")

    nvidia = ApiProvider(
        id="nv",
        name="NVIDIA",
        base_url="https://integrate.api.nvidia.com/v1",
        models=[],
    )
    nv_sync = sync_provider_listing(
        nvidia,
        [{"id": "nvidia/nemotron-mini"}],
        confirm_missing=True,
        now_iso="2026-11-13T12:00:00+09:00",
    )
    nv_entry = next(e for e in nv_sync.entries if e.model_id == "nvidia/nemotron-mini")
    assert nv_entry.price_class == "free"
    assert display_tier(nv_entry) == DisplayTier.FREE
    assert nvidia.model_meta["nvidia/nemotron-mini"]["price_class"] == "free"

    other = ApiProvider(
        id="other",
        name="Other",
        base_url="https://example.test/v1",
        models=[],
    )
    other_sync = sync_provider_listing(
        other,
        [{"id": "nvidia/nemotron-mini"}],
        confirm_missing=True,
        now_iso="2026-11-13T12:01:00+09:00",
    )
    other_entry = next(e for e in other_sync.entries if e.model_id == "nvidia/nemotron-mini")
    assert other_entry.price_class == "unknown"

    print("brand_roster_sync self-check ok")


if __name__ == "__main__":
    main()
