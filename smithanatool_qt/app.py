
import sys, time
from PySide6.QtWidgets import QApplication
from .main_window import MainWindow
from PySide6.QtCore import QTimer

def run():
    app = QApplication(sys.argv)

    t0 = time.perf_counter()
    win = MainWindow()
    print(f"MainWindow: {time.perf_counter() - t0:.3f}s", flush=True)

    # 2) опционально измеряем «тяжёлую» вкладку Transform
    try:
        # если реализовал ленивую инициализацию через _ensure_tab(...)
        t1 = time.perf_counter()
        win._ensure_tab("transform")
        print(f"TransformTab create: {time.perf_counter() - t1:.3f}s", flush=True)
    except AttributeError:
        # fallback: прямое создание без добавления во вкладки
        from smithanatool_qt.tabs.transform.tab import TransformTab
        t1 = time.perf_counter()
        tmp = TransformTab(win)  # создаём отдельно
        print(f"TransformTab (direct): {time.perf_counter() - t1:.3f}s", flush=True)
        tmp.deleteLater()  # сразу удаляем, чтобы не плодить UI

    win.show()
    QTimer.singleShot(0, win._realize_active_tab_later)
    return app.exec()

