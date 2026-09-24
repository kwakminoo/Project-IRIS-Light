"""Android 에뮬레이터 컨트롤 액션."""

from __future__ import annotations

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import EmulatorHost

def register_emulator_actions(window: EmulatorHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        _append_activity,
        _log,
        err_result,
        ok_result,
    )

    def emu_status(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import emulator_status

        return ok_result("emulator.status", emulator_status())

    def emu_launch(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import (
            AdbError,
            emulator_status,
            is_emulator_running,
            launch_emulator,
            read_launch_log_tail,
            restart_emulator_windowed,
        )

        headless = bool(a.get("headless", False))
        try:
            if is_emulator_running():
                from iris.system.android_emulator import is_emulator_headless

                if is_emulator_headless() and not headless:
                    proc = restart_emulator_windowed()
                    _log(window, "emulator.launch", True)
                    _append_activity(
                        window,
                        f"Android 에뮬레이터 재시작 (PID {proc.pid})",
                    )
                    _append_activity(
                        window,
                        "에뮬레이터 첫 기동·부팅에는 약간의 시간이 소요될 수 있습니다.",
                    )
                    return ok_result(
                        "emulator.launch",
                        {
                            "pid": proc.pid,
                            "restarted_windowed": True,
                            **emulator_status(),
                        },
                    )
                return ok_result(
                    "emulator.launch",
                    {"already_running": True, **emulator_status()},
                )
            proc = launch_emulator(headless=headless)
            _log(window, "emulator.launch", True)
            _append_activity(
                window,
                f"Android 에뮬레이터 시작 (PID {proc.pid})",
            )
            _append_activity(
                window,
                "에뮬레이터 첫 기동·부팅에는 약간의 시간이 소요될 수 있습니다.",
            )
            return ok_result(
                "emulator.launch",
                {"pid": proc.pid, **emulator_status()},
            )
        except (OSError, AdbError, FileNotFoundError) as exc:
            _log(window, "emulator.launch", False)
            tail = read_launch_log_tail(lines=20)
            detail = str(exc)
            if tail:
                detail = f"{detail}\n--- launch log ---\n{tail[:800]}"
            return err_result("emulator.launch", detail)

    def emu_wait_ready(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, emulator_status, wait_for_boot

        timeout_s = float(a.get("timeout_s") or 180)
        try:
            serial = wait_for_boot(timeout_s=timeout_s)
            _log(window, "emulator.wait_ready", True)
            return ok_result(
                "emulator.wait_ready",
                {"serial": serial, **emulator_status()},
            )
        except AdbError as exc:
            return err_result("emulator.wait_ready", str(exc))

    def emu_kill(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, emulator_status, kill_emulator

        try:
            killed = kill_emulator()
            _log(window, "emulator.kill", True)
            return ok_result("emulator.kill", {"killed": killed, **emulator_status()})
        except AdbError as exc:
            return err_result("emulator.kill", str(exc))

    def emu_install(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, install_apk

        apk = str(a.get("apk") or "").strip()
        if not apk:
            return err_result("emulator.install", "apk path required")
        try:
            output = install_apk(apk)
            _log(window, "emulator.install", True)
            return ok_result("emulator.install", {"apk": apk, "output": output})
        except AdbError as exc:
            return err_result("emulator.install", str(exc))

    def emu_start_app(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, start_app

        package = str(a.get("package") or "").strip()
        activity = str(a.get("activity") or "").strip()
        if not package:
            return err_result("emulator.start_app", "package required")
        # convenience: "설정" → Settings
        if package.lower() in ("settings", "설정", "설정앱"):
            package = "com.android.settings"
            activity = ""
        try:
            start_app(package, activity)
            _log(window, "emulator.start_app", True)
            return ok_result(
                "emulator.start_app",
                {"package": package, "activity": activity or None},
            )
        except AdbError as exc:
            return err_result("emulator.start_app", str(exc))

    def emu_key(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, press_key

        key = str(a.get("key") or "").strip()
        if not key:
            return err_result("emulator.key", "key required")
        try:
            press_key(key)
            return ok_result("emulator.key", {"key": key.upper()})
        except AdbError as exc:
            return err_result("emulator.key", str(exc))

    def emu_input_text(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, input_text

        if "text" not in a:
            return err_result("emulator.input_text", "text required")
        text = str(a.get("text") or "")
        try:
            input_text(text)
            return ok_result("emulator.input_text", {"text": text})
        except AdbError as exc:
            return err_result("emulator.input_text", str(exc))

    def _as_int(name: str, raw: object) -> int:
        if isinstance(raw, bool) or raw is None:
            raise ValueError(f"{name} must be int")
        return int(raw)

    def emu_tap(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, tap

        try:
            x = _as_int("x", a.get("x"))
            y = _as_int("y", a.get("y"))
            tap(x, y)
            return ok_result("emulator.tap", {"x": x, "y": y})
        except (AdbError, ValueError, TypeError) as exc:
            return err_result("emulator.tap", str(exc))

    def emu_swipe(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, swipe

        try:
            x1 = _as_int("x1", a.get("x1"))
            y1 = _as_int("y1", a.get("y1"))
            x2 = _as_int("x2", a.get("x2"))
            y2 = _as_int("y2", a.get("y2"))
            duration_ms = int(a.get("duration_ms") or 300)
            swipe(x1, y1, x2, y2, duration_ms=duration_ms)
            return ok_result(
                "emulator.swipe",
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms},
            )
        except (AdbError, ValueError, TypeError) as exc:
            return err_result("emulator.swipe", str(exc))

    def emu_screenshot(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, screenshot

        path = str(a.get("path") or "").strip()
        try:
            saved = screenshot(path)
            _log(window, "emulator.screenshot", True)
            return ok_result("emulator.screenshot", {"path": saved})
        except AdbError as exc:
            return err_result("emulator.screenshot", str(exc))

    def emu_ui_texts(_a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, ui_texts

        try:
            texts = ui_texts()
            return ok_result("emulator.ui_texts", {"texts": texts, "count": len(texts)})
        except AdbError as exc:
            return err_result("emulator.ui_texts", str(exc))

    def emu_tap_text(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, tap_text

        text = str(a.get("text") or "").strip()
        if not text:
            return err_result("emulator.tap_text", "text required")
        try:
            hit = tap_text(text, exact=bool(a.get("exact", False)))
            _log(window, "emulator.tap_text", True)
            return ok_result("emulator.tap_text", hit)
        except AdbError as exc:
            return err_result("emulator.tap_text", str(exc))

    def emu_play_install(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, play_install

        app = str(a.get("app") or a.get("package") or "").strip()
        if not app:
            return err_result("emulator.play_install", "app/package required")
        try:
            result = play_install(app, timeout_s=float(a.get("timeout_s") or 300))
            _log(window, "emulator.play_install", True)
            window._live_activity.append_instant_line(
                f"Play 설치 완료: {result['package']}"
            )
            return ok_result("emulator.play_install", result)
        except (AdbError, ValueError, TypeError) as exc:
            _log(window, "emulator.play_install", False)
            return err_result("emulator.play_install", str(exc))

    def emu_logcat(a: dict[str, Any]) -> dict[str, Any]:
        from iris.system.android_emulator import AdbError, logcat_tail

        try:
            lines_n = int(a.get("lines") or 100)
            filt = str(a.get("filter") or "").strip()
            rows = logcat_tail(lines_n, filt)
            return ok_result(
                "emulator.logcat_tail",
                {"lines": rows, "count": len(rows), "filter": filt or None},
            )
        except (AdbError, ValueError, TypeError) as exc:
            return err_result("emulator.logcat_tail", str(exc))

    reg.register("emulator.status", emu_status, summary="Android emulator status (AVD serials)")

    reg.register(
        "emulator.launch",
        emu_launch,
        summary="Launch IrisLight_Pixel Android emulator",
        risk="medium",
    )

    reg.register(
        "emulator.wait_ready",
        emu_wait_ready,
        summary="Wait until adb serial + boot_completed",
        risk="low",
    )

    reg.register(
        "emulator.kill",
        emu_kill,
        summary="Kill IrisLight_Pixel Android emulator",
        risk="medium",
    )

    reg.register(
        "emulator.install",
        emu_install,
        summary="adb install -r APK on emulator",
        risk="medium",
    )

    reg.register(
        "emulator.start_app",
        emu_start_app,
        summary="Start app by package (optional activity)",
        risk="medium",
    )

    reg.register(
        "emulator.key",
        emu_key,
        summary="Send keyevent HOME|BACK|ENTER|APP_SWITCH|POWER",
        risk="medium",
    )

    reg.register(
        "emulator.input_text",
        emu_input_text,
        summary="Type text via adb input text",
        risk="medium",
    )

    reg.register(
        "emulator.tap",
        emu_tap,
        summary="Tap screen at x,y",
        risk="medium",
    )

    reg.register(
        "emulator.swipe",
        emu_swipe,
        summary="Swipe from x1,y1 to x2,y2",
        risk="medium",
    )

    reg.register(
        "emulator.screenshot",
        emu_screenshot,
        summary="Capture emulator screenshot to file",
        risk="medium",
    )

    reg.register(
        "emulator.ui_texts",
        emu_ui_texts,
        summary="List on-screen texts via uiautomator (no coordinates needed)",
        risk="low",
    )

    reg.register(
        "emulator.tap_text",
        emu_tap_text,
        summary="Tap the on-screen element whose text/description matches",
        risk="medium",
    )

    reg.register(
        "emulator.play_install",
        emu_play_install,
        summary="Install app from Play Store via market:// deep link + UI tree",
        risk="medium",
    )

    reg.register(
        "emulator.logcat_tail",
        emu_logcat,
        summary="Read recent logcat lines (optional filter)",
        risk="low",
    )
