"""Listing/roster domain: parse, display tier, sync, retire. No HTTP/UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Mapping, Sequence

PriceClass = Literal["free", "paid", "unknown"]
Modality = Literal["chat", "image", "audio", "video", "embedding", "other", "unknown"]
Availability = Literal["ok", "unverified", "unavailable", ""]
ToolSupport = Literal["yes", "no", "unknown", ""]

_OFF_DOMAIN: frozenset[str] = frozenset({"image", "audio", "video", "embedding"})
_EMBED_ID_MARKERS: tuple[str, ...] = (
    "embedding",
    "embed-",
    "-embed",
    "text-embedding",
    "bge-",
    "e5-",
)


class DisplayTier(str, Enum):
    FREE = "free"
    OFF_DOMAIN = "off_domain"
    PAID = "paid"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ListingModel:
    id: str
    description: str = ""
    price_class: PriceClass = "unknown"
    modality: Modality = "unknown"
    raw: Mapping[str, object] = field(default_factory=dict)


@dataclass
class RosterEntry:
    model_id: str
    description: str = ""
    price_class: PriceClass = "unknown"
    modality: Modality = "unknown"
    availability: Availability = "unverified"
    tool_support: ToolSupport = "unknown"
    retired: bool = False
    retired_at: str = ""
    retire_evidence: str = ""
    listing_seen_at: str = ""
    price_refetch_done: bool = False


@dataclass(frozen=True)
class SyncResult:
    entries: tuple[RosterEntry, ...]
    added: tuple[str, ...]
    updated: tuple[str, ...]
    retired_ids: tuple[str, ...]
    needs_price_refetch: bool


def _as_mapping(item: Mapping[str, object] | object) -> Mapping[str, object]:
    if isinstance(item, Mapping):
        return item
    return {}


def _official_description(item: Mapping[str, object]) -> str:
    for key in ("description", "summary"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _price_zero(val: object) -> bool:
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return float(val) == 0.0
    text = str(val).strip()
    if not text:
        return False
    try:
        return float(text) == 0.0
    except ValueError:
        return False


def _price_positive(val: object) -> bool:
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return float(val) > 0.0
    text = str(val).strip()
    if not text:
        return False
    try:
        return float(text) > 0.0
    except ValueError:
        return False


def _infer_price_class(model_id: str, item: Mapping[str, object]) -> PriceClass:
    mid = (model_id or "").strip().lower()
    if mid.endswith(":free"):
        return "free"
    for key in ("is_free", "free"):
        if key in item and bool(item.get(key)):
            return "free"
    pricing = item.get("pricing")
    if isinstance(pricing, Mapping):
        prompt = pricing.get("prompt")
        completion = pricing.get("completion")
        if _price_positive(prompt) or _price_positive(completion):
            return "paid"
        if _price_zero(prompt) or _price_zero(completion):
            # both present and zero, or any explicit zero with no positive sibling
            if not _price_positive(prompt) and not _price_positive(completion):
                if prompt is not None or completion is not None:
                    return "free"
    return "unknown"


def _modality_from_token(token: str) -> Modality | None:
    t = token.strip().lower()
    if not t:
        return None
    if "embed" in t:
        return "embedding"
    if "image" in t or t in ("vision", "img"):
        return "image"
    if "audio" in t or "speech" in t or "tts" in t or "asr" in t:
        return "audio"
    if "video" in t:
        return "video"
    if "chat" in t or t in ("text", "text->text", "llm", "language"):
        return "chat"
    return None


def _collect_modality_tokens(item: Mapping[str, object]) -> list[str]:
    tokens: list[str] = []
    for key in ("modality", "type"):
        val = item.get(key)
        if isinstance(val, str):
            tokens.append(val)
        elif isinstance(val, (list, tuple)):
            tokens.extend(str(x) for x in val)
    arch = item.get("architecture")
    if isinstance(arch, Mapping):
        for key in ("modality", "output_modality", "type"):
            val = arch.get(key)
            if isinstance(val, str):
                tokens.append(val)
            elif isinstance(val, (list, tuple)):
                tokens.extend(str(x) for x in val)
    out = item.get("output_modalities")
    if isinstance(out, (list, tuple)):
        tokens.extend(str(x) for x in out)
    elif isinstance(out, str):
        tokens.append(out)
    return tokens


def _infer_modality(model_id: str, item: Mapping[str, object]) -> Modality:
    for token in _collect_modality_tokens(item):
        hit = _modality_from_token(token)
        if hit is not None:
            return hit
    mid = (model_id or "").lower()
    if any(m in mid for m in _EMBED_ID_MARKERS):
        return "embedding"
    return "unknown"


def parse_listing(item: Mapping[str, object] | object) -> ListingModel:
    data = _as_mapping(item)
    mid = str(data.get("id") or "").strip()
    return ListingModel(
        id=mid,
        description=_official_description(data),
        price_class=_infer_price_class(mid, data),
        modality=_infer_modality(mid, data),
        raw=dict(data),
    )


def parse_listings(payload: object) -> list[ListingModel]:
    if isinstance(payload, Mapping):
        items = payload.get("data")
        if not isinstance(items, list):
            return []
    elif isinstance(payload, list):
        items = payload
    else:
        return []
    out: list[ListingModel] = []
    for raw in items:
        parsed = parse_listing(raw)
        if parsed.id:
            out.append(parsed)
    return out


def display_tier(entry: RosterEntry) -> DisplayTier:
    if entry.modality in _OFF_DOMAIN:
        return DisplayTier.OFF_DOMAIN
    if entry.price_class == "paid":
        return DisplayTier.PAID
    if entry.price_class == "free":
        return DisplayTier.FREE
    return DisplayTier.UNKNOWN


def tier_sort_rank(tier: DisplayTier) -> int:
    return {
        DisplayTier.FREE: 0,
        DisplayTier.OFF_DOMAIN: 1,
        DisplayTier.PAID: 2,
        DisplayTier.UNKNOWN: 3,
    }[tier]


def sort_key(entry: RosterEntry) -> tuple:
    unavailable = 1 if entry.availability == "unavailable" else 0
    return (
        1 if entry.retired else 0,
        unavailable,
        tier_sort_rank(display_tier(entry)),
        entry.model_id.lower(),
    )


def sort_roster(entries: Sequence[RosterEntry]) -> list[RosterEntry]:
    return sorted(entries, key=sort_key)


def needs_price_refetch(entries: Sequence[RosterEntry]) -> bool:
    return any(
        e.price_class == "unknown" and not e.price_refetch_done and not e.retired
        for e in entries
    )


def mark_price_refetch_done(
    entries: Sequence[RosterEntry],
    model_ids: Sequence[str] | None = None,
) -> list[RosterEntry]:
    wanted = None if model_ids is None else set(model_ids)
    out: list[RosterEntry] = []
    for e in entries:
        if e.price_class == "unknown" and (wanted is None or e.model_id in wanted):
            out.append(_copy_entry(e, price_refetch_done=True))
        else:
            out.append(_copy_entry(e))
    return out


def _copy_entry(e: RosterEntry, **updates: object) -> RosterEntry:
    base = {
        "model_id": e.model_id,
        "description": e.description,
        "price_class": e.price_class,
        "modality": e.modality,
        "availability": e.availability,
        "tool_support": e.tool_support,
        "retired": e.retired,
        "retired_at": e.retired_at,
        "retire_evidence": e.retire_evidence,
        "listing_seen_at": e.listing_seen_at,
        "price_refetch_done": e.price_refetch_done,
    }
    base.update(updates)
    return RosterEntry(**base)  # type: ignore[arg-type]


def sync_from_listing(
    current: Sequence[RosterEntry],
    listings: Sequence[ListingModel],
    *,
    brand_id: str,
    confirm_missing: bool,
    now_iso: str = "",
) -> SyncResult:
    _ = brand_id
    by_id = {e.model_id: e for e in current}
    listed = {m.id: m for m in listings if m.id}
    added: list[str] = []
    updated: list[str] = []
    retired_ids: list[str] = []
    out: list[RosterEntry] = []

    for mid, listing in listed.items():
        existing = by_id.get(mid)
        if existing is None:
            out.append(
                RosterEntry(
                    model_id=mid,
                    description=listing.description,
                    price_class=listing.price_class,
                    modality=listing.modality,
                    listing_seen_at=now_iso,
                )
            )
            added.append(mid)
            continue
        revived = existing.retired
        availability = existing.availability
        if existing.availability == "unavailable":
            availability = "unverified"
        out.append(
            _copy_entry(
                existing,
                description=listing.description if listing.description else existing.description,
                price_class=listing.price_class,
                modality=listing.modality if listing.modality != "unknown" else existing.modality,
                availability=availability,
                retired=False,
                retired_at="" if revived else existing.retired_at,
                retire_evidence="" if revived else existing.retire_evidence,
                listing_seen_at=now_iso or existing.listing_seen_at,
                # new official price evidence resets refetch gate for this merge
                price_refetch_done=(
                    existing.price_refetch_done
                    if listing.price_class == "unknown"
                    else False
                ),
            )
        )
        updated.append(mid)

    for mid, existing in by_id.items():
        if mid in listed:
            continue
        if confirm_missing:
            out.append(
                _copy_entry(
                    existing,
                    retired=True,
                    retired_at=now_iso or existing.retired_at,
                    retire_evidence=existing.retire_evidence or "listing-missing",
                    availability="unavailable",
                )
            )
            retired_ids.append(mid)
        else:
            out.append(_copy_entry(existing))

    result_entries = tuple(out)
    return SyncResult(
        entries=result_entries,
        added=tuple(added),
        updated=tuple(updated),
        retired_ids=tuple(retired_ids),
        needs_price_refetch=needs_price_refetch(result_entries),
    )


def retire_on_http(
    current: Sequence[RosterEntry],
    *,
    model_id: str,
    status: int,
    evidence: str = "",
    now_iso: str = "",
) -> list[RosterEntry]:
    if status != 410:
        return [_copy_entry(e) for e in current]
    ev = evidence or "http-410"
    found = False
    out: list[RosterEntry] = []
    for e in current:
        if e.model_id == model_id:
            found = True
            out.append(
                _copy_entry(
                    e,
                    retired=True,
                    retired_at=now_iso or e.retired_at,
                    retire_evidence=ev,
                    availability="unavailable",
                )
            )
        else:
            out.append(_copy_entry(e))
    if not found:
        out.append(
            RosterEntry(
                model_id=model_id,
                retired=True,
                retired_at=now_iso,
                retire_evidence=ev,
                availability="unavailable",
            )
        )
    return out


def apply_probe(
    entry: RosterEntry,
    *,
    availability: Availability | None = None,
    tool_support: ToolSupport | None = None,
) -> RosterEntry:
    updates: dict[str, object] = {}
    if availability is not None:
        updates["availability"] = availability
    if tool_support is not None:
        updates["tool_support"] = tool_support
    # retired must stay unless listing evidence clears it in sync_from_listing
    return _copy_entry(entry, **updates)
