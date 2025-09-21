
from smithanatool_qt.app import run
from PySide6.QtCore import QSettings, QCoreApplication

QCoreApplication.setOrganizationName("Smithana")
QCoreApplication.setApplicationName("SmithanaTool")

if __name__ == "__main__":
    run()
