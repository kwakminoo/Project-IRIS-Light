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

    from iris.infrastructure import model_blurb_ko as mbk

    catalog_row = PickerModel(
        "api:x:nvidia/nemotron-3-ultra",
        "Nemotron Ultra",
        is_api=True,
        price_class="paid",
        modality="chat",
        listing_description="High-throughput English blurb from API listing",
    )
    catalog_blurb = _api_blurb(catalog_row)
    assert catalog_blurb.startswith("NVIDIA Nemotron 3 Ultra")
    assert mbk.has_hangul(catalog_blurb)
    assert "High-throughput" not in catalog_blurb

    _KO_STUB = "번역된 공식 무료 채팅"
    _original_translate = mbk.translate_en_to_ko
    mbk.translate_en_to_ko = lambda _text: _KO_STUB  # type: ignore[method-assign, return-value]
    try:
        translated_row = PickerModel(
            "api:x:nonsense-no-catalog",
            "weird",
            is_api=True,
            price_class="free",
            modality="chat",
            listing_description="Official free chat",
        )
        assert _api_blurb(translated_row) == _KO_STUB
    finally:
        mbk.translate_en_to_ko = _original_translate  # type: ignore[method-assign]

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

    from iris.ui.chat.model_picker_menu import BRAND_MIN_MODELS, split_picker_groups, sorted_picker_models

    tier_models = [
        PickerModel(
            f"api:t:mystery",
            "z-mystery",
            is_api=True,
            price_class="unknown",
            modality="chat",
        ),
        PickerModel(
            "api:t:paid-chat",
            "c-paid",
            is_api=True,
            price_class="paid",
            modality="chat",
        ),
        PickerModel(
            "api:t:embed",
            "b-embed",
            is_api=True,
            price_class="free",
            modality="embedding",
        ),
        PickerModel(
            "api:t:free-chat",
            "a-free",
            is_api=True,
            price_class="free",
            modality="chat",
        ),
    ]
    singles_tiered = list(tier_models)
    _local, _ol, _br, singles_out = split_picker_groups(singles_tiered)
    assert [m.runtime for m in singles_out] == [m.runtime for m in sorted(tier_models, key=picker_sort_key)]

    _labels = ["z-unk", "d-paid", "c-paid2", "b-embed", "a-free2", "a-free"]
    _pcs = ["unknown", "paid", "paid", "free", "free", "free"]
    _mods = ["chat", "chat", "chat", "embedding", "chat", "chat"]
    many_tier = [
        PickerModel(
            f"api:br:m-{i}",
            _labels[i],
            is_api=True,
            price_class=_pcs[i],
            modality=_mods[i],
            provider_name="BrandCo",
            provider_base="https://api.example/v1",
        )
        for i in range(BRAND_MIN_MODELS)
    ]
    assert len(many_tier) >= BRAND_MIN_MODELS
    _, _, brands_out, _ = split_picker_groups(many_tier)
    assert "br" in brands_out
    brand_order = [m.runtime for m in brands_out["br"]]
    expect = [m.runtime for m in sorted(many_tier, key=picker_sort_key)]
    assert brand_order == expect, (brand_order, expect)

    dialog_order = [m.runtime for m in sorted_picker_models(list(reversed(many_tier)))]
    assert dialog_order == expect

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
