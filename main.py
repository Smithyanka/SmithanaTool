import smithanatool_qt.resources.resources_rc
from smithanatool_qt.app import run
from PySide6.QtCore import QCoreApplication

QCoreApplication.setOrganizationName("Smithana")
QCoreApplication.setApplicationName("SmithanaTool")

if __name__ == "__main__":
    run()
