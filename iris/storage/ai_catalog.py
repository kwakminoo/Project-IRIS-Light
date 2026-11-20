"""AI Hub catalog — Iris fitness (tool-calling chat vs later)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from iris.storage.api_providers import FREE_LLM_OFFERS, ApiProvider, load_api_providers
from iris.storage.database import Database

AiModality = Literal["chat", "image", "audio", "video", "embedding", "other"]
AiFitness = Literal["iris_chat", "later"]


@dataclass(frozen=True)
class AiCatalogEntry:
    id: str
    label: str
    modality: AiModality
    fitness: AiFitness
    provider_id: str = ""
    model_id: str = ""
    base_url: str = ""
    limit_note: str = ""
    signup_url: str = ""


DEFERRED_MODALITY_STUBS: tuple[AiCatalogEntry, ...] = (
    AiCatalogEntry(
        id="stub:image",
        label="이미지 생성 (예정)",
        modality="image",
        fitness="later",
    ),
    AiCatalogEntry(
        id="stub:audio",
        label="음성 (예정)",
        modality="audio",
        fitness="later",
    ),
    AiCatalogEntry(
        id="stub:video",
        label="영상 생성 (예정)",
        modality="video",
        fitness="later",
    ),
    AiCatalogEntry(
        id="stub:embedding",
        label="임베딩 (예정)",
        modality="embedding",
        fitness="later",
    ),
)


def callable_for_iris_chat(entry: AiCatalogEntry) -> bool:
    return entry.fitness == "iris_chat" and entry.modality == "chat"


def fitness_for_probe(*, state: str, tool_support: str) -> AiFitness:
    if state == "ok" and tool_support == "yes":
        return "iris_chat"
    return "later"


def _offer_id(name: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"offer:{slug or 'unnamed'}"


def offers_as_catalog() -> list[AiCatalogEntry]:
    out: list[AiCatalogEntry] = []
    for offer in FREE_LLM_OFFERS:
        out.append(
            AiCatalogEntry(
                id=_offer_id(offer.name),
                label=offer.name,
                modality="chat",
                fitness="later",
                base_url=offer.base_url,
                limit_note=offer.limit_note,
                signup_url=offer.signup_url,
            )
        )
    return out


def entries_from_providers(providers: list[ApiProvider]) -> list[AiCatalogEntry]:
    out: list[AiCatalogEntry] = []
    for provider in providers:
        for model in provider.models:
            mid = str(model).strip()
            if not mid:
                continue
            state = provider.model_states.get(mid, "")
            tool = provider.tool_support.get(mid, "")
            out.append(
                AiCatalogEntry(
                    id=f"{provider.id}:{mid}",
                    label=f"{provider.name or provider.id} · {mid}",
                    modality="chat",
                    fitness=fitness_for_probe(state=state, tool_support=tool),
                    provider_id=provider.id,
                    model_id=mid,
                    base_url=(provider.resolved_base_url or provider.base_url or "").strip(),
                )
            )
    return out


def iris_chat_entries(entries: list[AiCatalogEntry]) -> list[AiCatalogEntry]:
    return [e for e in entries if callable_for_iris_chat(e)]


def later_entries(entries: list[AiCatalogEntry]) -> list[AiCatalogEntry]:
    return [e for e in entries if not callable_for_iris_chat(e)]


def build_catalog(db: Database | None) -> list[AiCatalogEntry]:
    seen: set[str] = set()
    out: list[AiCatalogEntry] = []
    for entry in (
        *offers_as_catalog(),
        *entries_from_providers(load_api_providers(db)),
        *DEFERRED_MODALITY_STUBS,
    ):
        if entry.id in seen:
            continue
        seen.add(entry.id)
        out.append(entry)
    return out
