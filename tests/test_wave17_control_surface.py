from types import SimpleNamespace
from unittest.mock import patch

import pytest

from iris.system.control_surface import ControlSurface
from iris.ui.control_bindings import mark_control_ready, start_control_surface, stop_control_surface


@pytest.mark.parametrize("http_enabled", [False, True])
def test_native_registry_survives_disabled_http_or_bind_failure(monkeypatch, http_enabled):
    from PyQt6.QtCore import QObject

    from iris.infrastructure import speak_capability

    monkeypatch.setenv("IRIS_CONTROL_ENABLED", str(int(http_enabled)))
    monkeypatch.setenv("IRIS_CONTROL_TOKEN", "test")
    window = QObject()
    window._live_activity = SimpleNamespace(append_instant_line=lambda _message: None)

    def register(_window, surface):
        surface.registry.register("test_action", lambda _args: {}, summary="Test action")

    with (
        patch("iris.ui.control_bindings._register_actions", side_effect=register),
        patch.object(ControlSurface, "start", side_effect=OSError("port unavailable")) as start,
        patch("iris.system.control_surface.clear_control_endpoint") as clear,
    ):
        try:
            surface = start_control_surface(window)
            assert surface is not None
            assert surface is speak_capability._BOUND_SURFACE
            assert surface.bound_port is None
            assert surface.booting
            mark_control_ready(window)
            assert not surface.booting
            assert surface.registry.invoke("test_action", {"trusted": True})["ok"]
            assert start.call_count == int(http_enabled)
        finally:
            stop_control_surface(window)
        clear.assert_not_called()
