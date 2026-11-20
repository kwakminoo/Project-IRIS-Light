"""model_blurb_ko display helper self-check (no network)."""

from __future__ import annotations

import time

import iris.infrastructure.model_blurb_ko as mbk


def main() -> None:
    assert mbk.has_hangul("한글 설명") is True
    assert mbk.has_hangul("English only") is False
    assert mbk.has_hangul("") is False

    catalog = mbk.display_api_description(
        "api:x:nvidia/nemotron-3-ultra",
        "High-throughput English blurb from API listing",
    )
    assert catalog.startswith("NVIDIA Nemotron 3 Ultra")
    assert mbk.has_hangul(catalog)

    hangul_listing = "공식 한국어 요약입니다."
    unchanged = mbk.display_api_description(
        "nonsense-runtime-xyz-404",
        hangul_listing,
    )
    assert unchanged == hangul_listing
    assert mbk.display_api_description("unknown", "") == ""
    assert mbk.translate_en_to_ko("") == ""

    calls: list[str] = []

    def stub_translate(text: str) -> str:
        calls.append(text)
        return f"[ko]{text}"

    original = mbk.translate_en_to_ko
    mbk.translate_en_to_ko = stub_translate  # type: ignore[method-assign]
    try:
        out = mbk.display_api_description(
            "nonsense-runtime-xyz-404",
            "Frontier reasoning model",
        )
        assert out == "[ko]Frontier reasoning model"
        assert calls == ["Frontier reasoning model"]
    finally:
        mbk.translate_en_to_ko = original  # type: ignore[method-assign]

    mbk._cache = {}
    listing_en = "Frontier reasoning model"
    t0 = time.perf_counter()
    miss_out = mbk.display_api_description("nonsense-runtime-xyz-404", listing_en)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2, f"display blocked {elapsed:.3f}s on cache miss"
    assert miss_out == listing_en, (miss_out, listing_en)

    print("model_blurb_ko self-check ok")


if __name__ == "__main__":
    main()
