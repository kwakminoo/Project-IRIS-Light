"""Picker colors/blurbs/sort follow roster meta (not tool_support primary)."""

from __future__ import annotations


def main() -> None:
    from iris.infrastructure.model_roster import DisplayTier, RosterEntry, display_tier, sort_key
    from iris.ui.chat.model_picker_menu import (
        PickerModel,
        _COLOR_MODEL_DEFAULT,
        _COLOR_MODEL_NO_TOOLS,
        _COLOR_MODEL_PRO,
        _COLOR_MODEL_UNKNOWN,
        _api_blurb,
        _roster_aware,
        picker_sort_key,
        picker_tier_color,
    )

    free = PickerModel(
        "api:x:free-chat",
        "free-chat",
        is_api=True,
        supports_tools=False,
        tool_support="no",
        price_class="free",
        modality="chat",
        listing_description="Official free chat",
    )
    paid = PickerModel(
        "api:x:paid-chat",
        "paid-chat",
        is_api=True,
        price_class="paid",
        modality="chat",
        listing_description="Official paid",
    )
    embed = PickerModel(
        "api:x:embed",
        "embed",
        is_api=True,
        price_class="free",
        modality="embedding",
    )
    unknown = PickerModel(
        "api:x:mystery",
        "mystery",
        is_api=True,
        price_class="unknown",
        modality="unknown",
        tool_support="unknown",
    )

    assert picker_tier_color(free) == _COLOR_MODEL_DEFAULT
    assert picker_tier_color(paid) == _COLOR_MODEL_PRO
    assert picker_tier_color(embed) == _COLOR_MODEL_UNKNOWN
    assert picker_tier_color(unknown) == _COLOR_MODEL_NO_TOOLS

    assert display_tier(
        RosterEntry(model_id="f", price_class="free", modality="chat")
    ) == DisplayTier.FREE
    assert _api_blurb(free) == "Official free chat"
    empty_desc = PickerModel(
        "api:x:bare",
        "bare",
        is_api=True,
        price_class="free",
        modality="chat",
        listing_description="",
        tool_support="yes",
    )
    blurb = _api_blurb(empty_desc)
    assert "Official" not in blurb
    assert "도구" in blurb
    assert "web" not in blurb.lower()
    assert "invent" not in blurb.lower()

    # tools=no must not override free blue
    assert free.price_class == "free" and free.tool_support == "no"
    assert picker_tier_color(free) == _COLOR_MODEL_DEFAULT

    # sort: free before unknown; unavailable after usable
    a = RosterEntry(model_id="z-unknown", price_class="unknown", modality="chat")
    b = RosterEntry(model_id="a-free", price_class="free", modality="chat")
    c = RosterEntry(
        model_id="b-free-dead",
        price_class="free",
        modality="chat",
        availability="unavailable",
    )
    ordered = sorted([a, c, b], key=sort_key)
    assert [e.model_id for e in ordered] == ["a-free", "z-unknown", "b-free-dead"]

    # Boot mixes roster-aware API rows with legacy Ollama rows; sort must not TypeError.
    api_row = PickerModel(
        "api:x:free-chat",
        "free-chat",
        is_api=True,
        price_class="free",
        modality="chat",
    )
    legacy_ollama = PickerModel("gemma4:latest", "gemma4:latest")
    assert _roster_aware(api_row) and not _roster_aware(legacy_ollama)
    mixed = [api_row, legacy_ollama]
    mixed.sort(key=picker_sort_key)
    for m in mixed:
        key = picker_sort_key(m)
        assert len(key) == 4, key
        assert all(isinstance(key[i], int) for i in (0, 1, 2)), key
        assert isinstance(key[3], str), key

    from iris.infrastructure.ollama_client import OllamaModelInfo

    info = OllamaModelInfo(
        name="api:x:m",
        listing_description="Official only",
        price_class="free",
        modality="chat",
        retired=False,
    )
    assert info.listing_description == "Official only"
    assert info.price_class == "free"
    print("model_picker_roster self-check ok")


if __name__ == "__main__":
    main()
