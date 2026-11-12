"""Domain self-check for model_roster (parse / tier / sync / retire)."""

from __future__ import annotations

from iris.infrastructure.model_roster import (
    DisplayTier,
    ListingModel,
    RosterEntry,
    apply_probe,
    display_tier,
    mark_price_refetch_done,
    needs_price_refetch,
    parse_listing,
    parse_listings,
    retire_on_http,
    sort_roster,
    sync_from_listing,
    tier_sort_rank,
)


def main() -> None:
    bare = parse_listing({"id": "org/plain-model"})
    assert bare.id == "org/plain-model"
    assert bare.description == ""
    assert bare.price_class == "unknown"
    assert bare.modality == "unknown"

    free_suffix = parse_listing(
        {
            "id": "meta-llama/llama-3.1-8b-instruct:free",
            "description": "Llama 3.1 8B free tier",
        }
    )
    assert free_suffix.price_class == "free"
    assert free_suffix.description == "Llama 3.1 8B free tier"

    free_price = parse_listing(
        {
            "id": "provider/zero-cost",
            "summary": "Official summary only",
            "pricing": {"prompt": "0", "completion": 0},
        }
    )
    assert free_price.price_class == "free"
    assert free_price.description == "Official summary only"

    paid = parse_listing(
        {
            "id": "provider/paid-chat",
            "pricing": {"prompt": "0.0001", "completion": "0.0002"},
            "architecture": {"modality": "text->text"},
        }
    )
    assert paid.price_class == "paid"
    assert paid.modality == "chat"

    embed = parse_listing(
        {
            "id": "provider/text-embedding-3",
            "type": "embedding",
            "pricing": {"prompt": "0", "completion": "0"},
        }
    )
    assert embed.modality == "embedding"
    assert embed.price_class == "free"

    image = parse_listing(
        {
            "id": "provider/dall-e",
            "output_modalities": ["image"],
        }
    )
    assert image.modality == "image"

    listings = parse_listings(
        {
            "data": [
                {"id": "a"},
                {"name": "no-id"},
                {"id": "b", "description": "B"},
            ]
        }
    )
    assert [m.id for m in listings] == ["a", "b"]
    assert listings[1].description == "B"

    free_chat = RosterEntry(
        model_id="free-chat",
        price_class="free",
        modality="chat",
        description="Official free chat",
    )
    assert display_tier(free_chat) == DisplayTier.FREE

    free_embed = RosterEntry(
        model_id="free-embed",
        price_class="free",
        modality="embedding",
        tool_support="yes",
    )
    assert display_tier(free_embed) == DisplayTier.OFF_DOMAIN

    paid_chat = RosterEntry(model_id="paid-chat", price_class="paid", modality="chat")
    assert display_tier(paid_chat) == DisplayTier.PAID

    unknown = RosterEntry(model_id="unk", price_class="unknown", modality="chat")
    assert display_tier(unknown) == DisplayTier.UNKNOWN

    assert tier_sort_rank(DisplayTier.FREE) == 0
    assert tier_sort_rank(DisplayTier.OFF_DOMAIN) == 1
    assert tier_sort_rank(DisplayTier.PAID) == 2
    assert tier_sort_rank(DisplayTier.UNKNOWN) == 3

    sorted_ids = [
        e.model_id
        for e in sort_roster([unknown, free_chat, paid_chat, free_embed])
    ]
    assert sorted_ids == ["free-chat", "free-embed", "paid-chat", "unk"]

    current = [
        RosterEntry(model_id="keep", price_class="unknown", modality="chat"),
        RosterEntry(model_id="gone", price_class="free", modality="chat"),
    ]
    partial = sync_from_listing(
        current,
        [ListingModel(id="keep", price_class="free", modality="chat", description="K")],
        brand_id="brand",
        confirm_missing=False,
        now_iso="2026-11-12T00:00:00+09:00",
    )
    assert {e.model_id for e in partial.entries} == {"keep", "gone"}
    assert not any(e.retired for e in partial.entries if e.model_id == "gone")
    keep = next(e for e in partial.entries if e.model_id == "keep")
    assert keep.price_class == "free"
    assert keep.description == "K"

    confirmed = sync_from_listing(
        current,
        [ListingModel(id="keep", price_class="free", modality="chat")],
        brand_id="brand",
        confirm_missing=True,
        now_iso="2026-11-12T01:00:00+09:00",
    )
    assert {e.model_id for e in confirmed.entries} == {"keep", "gone"}
    gone = next(e for e in confirmed.entries if e.model_id == "gone")
    assert gone.retired is True
    assert gone.availability == "unavailable"
    assert "gone" in confirmed.retired_ids

    still = sync_from_listing(
        confirmed.entries,
        [ListingModel(id="keep", price_class="free", modality="chat")],
        brand_id="brand",
        confirm_missing=False,
        now_iso="2026-11-12T02:00:00+09:00",
    )
    gone2 = next(e for e in still.entries if e.model_id == "gone")
    assert gone2.retired is True

    revived = sync_from_listing(
        confirmed.entries,
        [
            ListingModel(id="keep", price_class="free", modality="chat"),
            ListingModel(id="gone", price_class="free", modality="chat", description="back"),
        ],
        brand_id="brand",
        confirm_missing=True,
        now_iso="2026-11-12T03:00:00+09:00",
    )
    gone3 = next(e for e in revived.entries if e.model_id == "gone")
    assert gone3.retired is False
    assert gone3.description == "back"
    assert gone3.listing_seen_at == "2026-11-12T03:00:00+09:00"

    httped = retire_on_http(
        [RosterEntry(model_id="eol", price_class="paid", modality="chat", availability="ok")],
        model_id="eol",
        status=410,
        evidence="http-410",
        now_iso="2026-11-12T04:00:00+09:00",
    )
    eol = httped[0]
    assert eol.retired is True
    assert eol.availability == "unavailable"
    assert eol.retire_evidence == "http-410"

    probed = apply_probe(eol, availability="ok", tool_support="yes")
    assert probed.retired is True
    assert probed.availability == "ok"
    assert probed.tool_support == "yes"

    unk_entries = [
        RosterEntry(model_id="u1", price_class="unknown", modality="chat"),
        RosterEntry(model_id="u2", price_class="free", modality="chat"),
    ]
    assert needs_price_refetch(unk_entries) is True
    marked = mark_price_refetch_done(unk_entries)
    assert needs_price_refetch(marked) is False
    assert all(e.price_refetch_done for e in marked if e.model_id == "u1")

    empty_blurb = parse_listing({"id": "x", "name": "not-a-description"})
    assert empty_blurb.description == ""

    print("model_roster self-check ok")


if __name__ == "__main__":
    main()
