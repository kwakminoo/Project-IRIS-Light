"""에뮬레이터 adb 헬퍼 스모크 (에뮬 없어도 dry-run).

  py -3 -m iris.ui._check_emulator_adb
"""

from __future__ import annotations


def main() -> int:
    from iris.system.android_emulator import (
        AVD_NAME,
        AdbError,
        _escape_adb_input_text,
        _has_existing_userdata,
        _KEYEVENT_CODES,
        _MIN_FREE_BYTES_EXISTING,
        _MIN_FREE_BYTES_FRESH,
        _sdk_root,
        adb_exe,
        avd_config_path,
        emulator_status,
        input_text,
        launch_log_path,
    )

    assert _escape_adb_input_text("hello world") == "hello%sworld"
    assert _KEYEVENT_CODES["BACK"] == 4
    sdk = str(_sdk_root())
    assert "Sdk" in sdk
    st = emulator_status()
    assert st["avd"] == AVD_NAME
    assert st["phase"] in ("stopped", "starting", "booting", "ready")
    assert "adb_ready" in st and "boot_completed" in st
    assert "keyboard_hint" in st
    need = _MIN_FREE_BYTES_EXISTING if _has_existing_userdata() else _MIN_FREE_BYTES_FRESH
    assert need >= _MIN_FREE_BYTES_EXISTING
    cfg = avd_config_path()
    if cfg.is_file():
        text = cfg.read_text(encoding="utf-8")
        assert "hw.keyboard=yes" in text
        assert "hw.gpu.enabled=yes" in text
    try:
        input_text("한글테스트")
        raise AssertionError("expected AdbError for Hangul")
    except AdbError as exc:
        assert "non-ASCII" in str(exc) or "IME" in str(exc)
    print("adb:", adb_exe(), "exists=", adb_exe().is_file())
    print("status:", st)
    print("launch_log:", launch_log_path())
    print("userdata_existing:", _has_existing_userdata(), "need_bytes:", need)

    import iris.ui.control_bindings as cb

    src = open(cb.__file__, encoding="utf-8").read()
    names_expected = {
        "emulator.status",
        "emulator.launch",
        "emulator.wait_ready",
        "emulator.kill",
        "emulator.install",
        "emulator.start_app",
        "emulator.key",
        "emulator.input_text",
        "emulator.tap",
        "emulator.swipe",
        "emulator.screenshot",
        "emulator.ui_texts",
        "emulator.tap_text",
        "emulator.play_install",
        "emulator.logcat_tail",
    }
    missing = [n for n in sorted(names_expected) if f'"{n}"' not in src]
    assert not missing, missing
    print("control_bindings emulator.* actions: ok")
    print("_check_emulator_adb ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
