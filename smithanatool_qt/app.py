import sys, time
from PySide6.QtWidgets import QApplication
from smithanatool_qt.main.main_window import MainWindow
from smithanatool_qt.graphic.theme import apply_dark_theme

def run():
    app = QApplication(sys.argv)

    t0 = time.perf_counter()
    win = MainWindow()
    print(f"MainWindow: {time.perf_counter() - t0:.3f}s", flush=True)

    win.show()
    return app.exec()