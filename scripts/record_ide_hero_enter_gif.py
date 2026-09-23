"""IRIS IDE 히어로 진입 연출(void → 구체 글리치 → 타이틀)을 GIF로 저장.

  .venv\\Scripts\\python.exe scripts\\record_ide_hero_enter_gif.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PIL import Image  # noqa: E402

from iris.ui.window.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "iris" / "assets" / "ide_hero_enter.gif"
DESKTOP = Path.home() / "Desktop" / "ide_hero_enter.gif"
FPS = 15
FRAME_MS = int(1000 / FPS)
TARGET_W = 960
PRE_HOLD_MS = 700
POST_HOLD_MS = 1100


def _qimage_to_pil(img: QImage) -> Image.Image:
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(img.sizeInBytes())
    return Image.frombytes("RGBA", (w, h), bytes(ptr)).convert("RGB")


def _save_gif(frames: list[Image.Image], path: Path) -> None:
    """용량을 위해 짝수 프레임만 쓰고 720w + 128색으로 줄인다."""
    kept = frames[::2] if len(frames) > 40 else frames
    w = 720
    quantized: list[Image.Image] = []
    for f in kept:
        nh = max(1, int(f.height * w / f.width))
        r = f.resize((w, nh), Image.Resampling.LANCZOS)
        quantized.append(r.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    duration = int(1000 / (FPS / 2))
    path.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        path,
        save_all=True,
        append_images=quantized[1:],
        duration=duration,
        loop=0,
        optimize=True,
    )


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(test_mode=True)
    win.resize(1280, 800)
    win.show()
    app.processEvents()

    # preferred IDE가 cursor면 히어로 세션이 즉시 clear → 연출 중단
    win._current_preferred_ide = lambda: "iris_ide"  # type: ignore[method-assign]
    win._ide_session_watch.stop()

    core = win._viz.particle_core()
    core.set_boot_reveal(1.0)
    core.set_boot_glitch(0.0)
    core.start()
    win._viz.request_sync_orb_anchor("gif_record")
    app.processEvents()

    frames: list[Image.Image] = []
    finished = {"yes": False}

    def grab() -> None:
        pix = win.grab()
        im = _qimage_to_pil(pix.toImage())
        if im.width != TARGET_W:
            nh = max(1, int(im.height * TARGET_W / im.width))
            im = im.resize((TARGET_W, nh), Image.Resampling.LANCZOS)
        frames.append(im)

    capture = QTimer()
    capture.setInterval(FRAME_MS)
    capture.timeout.connect(grab)

    def save_and_quit() -> None:
        if finished["yes"]:
            return
        finished["yes"] = True
        capture.stop()
        grab()
        if len(frames) < 8:
            print(f"ERROR: too few frames ({len(frames)})")
            app.exit(1)
            return
        _save_gif(frames, OUT)
        _save_gif(frames, DESKTOP)
        print(
            f"saved {OUT} raw_frames={len(frames)} "
            f"bytes={OUT.stat().st_size} mode={win._ui_mode} "
            f"hero={win._ide_hero.isVisible()} left={win._left_sidebar.isVisible()}"
        )
        app.quit()

    orig_done = win._on_ide_hero_reveal_done

    def on_reveal_done() -> None:
        print(
            "reveal_done",
            "mode=",
            win._ui_mode,
            "hero=",
            win._ide_hero.isVisible(),
            "left=",
            win._left_sidebar.isVisible(),
        )
        orig_done()
        QTimer.singleShot(POST_HOLD_MS, save_and_quit)

    win._on_ide_hero_reveal_done = on_reveal_done  # type: ignore[method-assign]

    def start_enter() -> None:
        capture.start()
        grab()
        win._enter_iris_ide_hero(source="icon")
        QTimer.singleShot(8000, save_and_quit)

    QTimer.singleShot(PRE_HOLD_MS, start_enter)
    code = app.exec()
    if code:
        raise SystemExit(code)
    if not OUT.is_file():
        raise SystemExit("gif not written")


if __name__ == "__main__":
    main()
