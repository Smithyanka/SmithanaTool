
import sys, time
from PySide6.QtWidgets import QApplication
from .main_window import MainWindow
from PySide6.QtCore import QTimer

def run():
    app = QApplication(sys.argv)

    t0 = time.perf_counter()
    win = MainWindow()
    print(f"MainWindow: {time.perf_counter() - t0:.3f}s", flush=True)


    win.show()
    return app.exec()

