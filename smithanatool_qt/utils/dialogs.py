
from PySide6.QtWidgets import QFileDialog, QMessageBox, QColorDialog, QWidget

def ask_open_files(parent: QWidget, caption: str = "Выберите файлы", filter: str = "Все файлы (*.*)"):
    return QFileDialog.getOpenFileNames(parent, caption, filter=filter)

def ask_open_dir(parent: QWidget, caption: str = "Выберите папку"):
    return QFileDialog.getExistingDirectory(parent, caption)

def ask_save_file(parent: QWidget, caption: str = "Сохранить как", filter: str = "Все файлы (*.*)"):
    return QFileDialog.getSaveFileName(parent, caption, filter=filter)

def info(parent: QWidget, title: str, text: str):
    QMessageBox.information(parent, title, text)

def warn(parent: QWidget, title: str, text: str):
    QMessageBox.warning(parent, title, text)

def error(parent: QWidget, title: str, text: str):
    QMessageBox.critical(parent, title, text)

def ask_yes_no(parent: QWidget, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

def pick_color(parent: QWidget):
    return QColorDialog.getColor(parent=parent)
