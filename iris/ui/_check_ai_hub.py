"""AI Hub 셸 계약 — 헤더 아이콘, 설정에서 LLM 분리, 허브 다이얼로그.

  .venv\\Scripts\\python.exe -m iris.ui._check_ai_hub
"""

from __future__ import annotations

import inspect
from pathlib import Path


def _check_drag_tab_ai_between_profile_and_settings() -> None:
    from iris.ui.widgets import drag_tab as dt

    src = Path(dt.__file__).read_text(encoding="utf-8")
    assert "ai_hub_clicked" in src or "ai_clicked" in src, "DragTab needs AI hub signal"
    assert "_btn_ai" in src or "_btn_ai_hub" in src, "DragTab needs AI button"
    # profile → ai → settings 순
    p = src.find("_btn_profile")
    a = src.find("_btn_ai")
    if a < 0:
        a = src.find("_btn_ai_hub")
    s = src.find("_btn_settings")
    assert 0 <= p < a < s, (p, a, s)


def _check_settings_api_box_has_no_llm_providers() -> None:
    from iris.ui.settings import settings_dialog as sd

    src = inspect.getsource(sd.SettingsDialog._build_api_box)
    assert "_build_api_providers_box" not in src, src
    assert "_build_search_api_box" in src
    assert "_build_calendar_api_box" in src


def _check_ai_hub_dialog_toplevel_open() -> None:
    from iris.ui.window import main_window as mw

    assert hasattr(mw.MainWindow, "_open_ai_hub_dialog")
    src = inspect.getsource(mw.MainWindow._open_ai_hub_dialog)
    assert "None" in src and ("0xC0000409" in src or "독립" in src or "top-level" in src or "parent" in src)


def _check_ai_hub_has_models_and_analytics() -> None:
    import iris.ui.ai_hub.ai_hub_dialog as mod

    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "Analytics" in text or "분석" in text
    assert "LLM" in text or "모델" in text or "Models" in text or "AI" in text
    assert "configure_hud_dialog" in text


def _check_failover_lives_in_ai_hub_not_settings() -> None:
    """Phase A: 모델 자동 전환 UI는 AI Hub, History만 설정."""
    import iris.ui.ai_hub.ai_hub_dialog as hub
    import iris.ui.settings.history_failover_box as hist

    hub_text = Path(hub.__file__).read_text(encoding="utf-8")
    assert "routing" in hub_text.lower() or "RoutingPanel" in hub_text or "failover" in hub_text.lower()

    hist_src = Path(hist.__file__).read_text(encoding="utf-8")
    # History 박스는 체인 추가 UI를 더 이상 소유하지 않는다
    assert "전환할 모델 이름" not in hist_src
    assert "모델 자동 전환 사용" not in hist_src

    from iris.ui.ai_hub import routing_panel as rp

    rp_text = Path(rp.__file__).read_text(encoding="utf-8")
    assert "모델 자동 전환" in rp_text or "failover" in rp_text.lower()
    assert "save_failover" in rp_text or "persist" in rp_text


def _check_route_cooldown_book() -> None:
    """freellmapi식 쿨다운 — Iris 소유 RouteCooldownBook."""
    from iris.runtime.model_failover import RouteCooldownBook, RouteTarget

    book = RouteCooldownBook()
    t = RouteTarget(model="m1", backend="api")
    assert book.is_cool(t) is False
    book.mark_cool(t, until_monotonic=1.0)
    assert book.is_cool(t, now_monotonic=0.5) is True
    assert book.is_cool(t, now_monotonic=1.5) is False
    hot = RouteTarget(model="m2", backend="api")
    kept = book.filter_ready([t, hot], now_monotonic=0.5)
    assert [x.model for x in kept] == ["m2"]


def _check_ai_catalog_fitness() -> None:
    """Phase B: 도구호출·상태 기준 iris_chat vs later."""
    from iris.storage.ai_catalog import (
        AiCatalogEntry,
        fitness_for_probe,
        iris_chat_entries,
        later_entries,
        offers_as_catalog,
    )

    assert fitness_for_probe(state="ok", tool_support="yes") == "iris_chat"
    assert fitness_for_probe(state="ok", tool_support="no") == "later"
    assert fitness_for_probe(state="unavailable", tool_support="yes") == "later"
    assert fitness_for_probe(state="ok", tool_support="unknown") == "later"

    offers = offers_as_catalog()
    assert offers, "FREE_LLM_OFFERS must seed catalog"
    assert all(e.modality == "chat" for e in offers)

    mixed = [
        AiCatalogEntry(
            id="a",
            label="chat-ok",
            modality="chat",
            fitness="iris_chat",
            model_id="m-ok",
        ),
        AiCatalogEntry(
            id="b",
            label="img",
            modality="image",
            fitness="later",
            model_id="img-1",
        ),
        AiCatalogEntry(
            id="c",
            label="no-tools",
            modality="chat",
            fitness="later",
            model_id="m-no",
        ),
    ]
    chat = iris_chat_entries(mixed)
    late = later_entries(mixed)
    assert [e.id for e in chat] == ["a"]
    assert {e.id for e in late} == {"b", "c"}


def _check_ai_hub_shows_catalog_sections() -> None:
    import iris.ui.ai_hub.ai_hub_dialog as hub

    text = Path(hub.__file__).read_text(encoding="utf-8")
    assert "CatalogPanel" in text or "catalog" in text.lower()
    from iris.ui.ai_hub import catalog_panel as cp

    cp_text = Path(cp.__file__).read_text(encoding="utf-8")
    assert "Iris 채팅" in cp_text or "iris_chat" in cp_text or "채팅용" in cp_text
    assert "나중" in cp_text or "later" in cp_text.lower()


def _check_ai_analytics_aggregates() -> None:
    """Phase C: 샘플 → 요청량·성공률·토큰·평균 지연."""
    from iris.storage.ai_analytics import (
        AiCallSample,
        aggregate_stats,
        record_sample,
        load_samples,
    )
    from iris.storage.database import Database
    import tempfile
    from pathlib import Path as P

    path = P(tempfile.mkdtemp()) / "ai_analytics_test.db"
    db = Database(path)
    db.initialize()
    record_sample(
        db,
        AiCallSample(
            runtime_model="api:x:m1",
            ok=True,
            latency_ms=100,
            tokens_in=10,
            tokens_out=20,
        ),
    )
    record_sample(
        db,
        AiCallSample(
            runtime_model="api:x:m1",
            ok=False,
            latency_ms=50,
            tokens_in=5,
            tokens_out=0,
        ),
    )
    samples = load_samples(db)
    assert len(samples) >= 2
    stats = aggregate_stats(samples)
    assert stats.requests == 2
    assert abs(stats.success_rate - 0.5) < 1e-9
    assert stats.tokens_in == 15
    assert stats.tokens_out == 20
    assert abs(stats.avg_latency_ms - 75.0) < 1e-9


def _check_ai_hub_analytics_panel_live() -> None:
    import iris.ui.ai_hub.ai_hub_dialog as hub

    text = Path(hub.__file__).read_text(encoding="utf-8")
    assert "AnalyticsPanel" in text or "analytics_panel" in text
    from iris.ui.ai_hub import analytics_panel as ap

    ap_text = Path(ap.__file__).read_text(encoding="utf-8")
    for needle in ("요청", "성공", "토큰", "지연"):
        assert needle in ap_text, needle


def _check_finish_turn_records_analytics() -> None:
    """채팅 턴 종료 경로에 analytics 기록이 붙어 있는지."""
    from iris.ui.window import main_window as mw
    import inspect

    src = inspect.getsource(mw.MainWindow._finish_current_turn)
    assert "record_sample" in src or "ai_analytics" in src


def _check_deferred_modalities_expanded() -> None:
    """Phase D: 이미지·음성·영상·임베딩 등이 later로 목록에만 있다."""
    from iris.storage.ai_catalog import (
        DEFERRED_MODALITY_STUBS,
        build_catalog,
        callable_for_iris_chat,
        later_entries,
    )

    modalities = {e.modality for e in DEFERRED_MODALITY_STUBS}
    for need in ("image", "audio", "video", "embedding"):
        assert need in modalities, need
    assert all(e.fitness == "later" for e in DEFERRED_MODALITY_STUBS)
    assert all(not callable_for_iris_chat(e) for e in DEFERRED_MODALITY_STUBS)

    catalog = build_catalog(None)
    deferred = [e for e in later_entries(catalog) if e.id.startswith("stub:")]
    assert len(deferred) >= 4
    for e in deferred:
        assert not callable_for_iris_chat(e)


def _check_catalog_panel_groups_deferred() -> None:
    from iris.ui.ai_hub import catalog_panel as cp

    text = Path(cp.__file__).read_text(encoding="utf-8")
    assert "이미지" in text or "image" in text.lower()
    assert "음성" in text or "audio" in text.lower() or "영상" in text or "임베딩" in text


def main() -> None:
    _check_drag_tab_ai_between_profile_and_settings()
    _check_settings_api_box_has_no_llm_providers()
    _check_ai_hub_dialog_toplevel_open()
    _check_ai_hub_has_models_and_analytics()
    _check_failover_lives_in_ai_hub_not_settings()
    _check_route_cooldown_book()
    _check_ai_catalog_fitness()
    _check_ai_hub_shows_catalog_sections()
    _check_ai_analytics_aggregates()
    _check_ai_hub_analytics_panel_live()
    _check_finish_turn_records_analytics()
    _check_deferred_modalities_expanded()
    _check_catalog_panel_groups_deferred()
    print("ai_hub self-check ok")


if __name__ == "__main__":
    main()
