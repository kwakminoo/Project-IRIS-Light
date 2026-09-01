"""IRIS IDE companion 80:20 tile geometry (PyQt, no live Theia required)."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow

from iris.system.ide_tiler import (
    compute_tile_rects,
    read_qt_window_rect,
    tiles_are_flush,
    tiles_have_overlap,
    tile_iris_ide_and_iris,
    work_area_for,
)
from iris.ui.workspaces.iris_ide_window import IrisIdeWindow


def main() -> int:
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    iris = QMainWindow()
    iris.setWindowTitle("Iris Light")
    iris.resize(900, 700)
    iris.show()
    ide = IrisIdeWindow()
    ide.show()
    app.processEvents()

    area = work_area_for(iris)
    tiles = compute_tile_rects(area, ide_ratio=0.8)
    assert tiles_are_flush(tiles.ide, tiles.iris)
    assert tiles.ide.width() + tiles.iris.width() == area.width()

    ok, err = tile_iris_ide_and_iris(ide, iris, ide_ratio=0.8)
    assert ok, err
    app.processEvents()

    ide_geo = read_qt_window_rect(ide) or ide.geometry()
    iris_geo = read_qt_window_rect(iris) or iris.geometry()
    total = area.width()
    expected_ide = int(total * 0.8)
    assert ide_geo.width() == expected_ide, (ide_geo.width(), expected_ide)
    assert iris_geo.width() == total - expected_ide, (iris_geo.width(), total - expected_ide)
    assert tiles_are_flush(ide_geo, iris_geo), (ide_geo, iris_geo)
    assert not tiles_have_overlap(ide_geo, iris_geo), (ide_geo, iris_geo)
    assert ide_geo.width() + iris_geo.width() == total
    iris.close()
    app.processEvents()
    print("iris_ide_companion_tile check ok", tiles.ide, tiles.iris)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
