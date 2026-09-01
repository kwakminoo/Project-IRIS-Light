"""IRIS GUI startup smoke — fast MainWindow init, no WebEngine at boot."""



from __future__ import annotations



import sys

import time



from iris.ui.qt_bootstrap import ensure_qt_webengine_ready





def main() -> None:

    ensure_qt_webengine_ready()

    from PyQt6.QtWidgets import QApplication



    app = QApplication.instance() or QApplication(sys.argv)

    from iris.ui.window.main_window import MainWindow



    t0 = time.monotonic()

    win = MainWindow(test_mode=True)

    elapsed = time.monotonic() - t0

    assert elapsed < 8.0, f"MainWindow init too slow: {elapsed:.1f}s"

    win.show()

    app.processEvents()

    win.close()

    app.processEvents()

    print("iris_startup ok", f"init={elapsed:.2f}s")





if __name__ == "__main__":

    main()

