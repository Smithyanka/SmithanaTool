from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

ACCENT       = QColor(35, 135, 213)  # (выделение)
ACCENT_DARK  = QColor(35, 135, 213)  # (нажатие кнопки)
ACCENT_DIM   = QColor(35, 135, 213)  # (края кнопки)

BG_WINDOW    = QColor(24, 24, 24)     # (главное окно)
BG_BASE      = QColor(31, 31, 31)    # (впадины)
BG_ALT       = QColor(20, 28, 44)    #  (alternate rows / panels)
BG_BUTTON    = QColor(31, 31, 31)    # (кнопки)
TXT_MAIN     = QColor(229, 231, 235) #
TXT_DIM      = QColor(64, 64, 64)       #
BORDER_DIM   = QColor(69, 69, 69)    # (бордюры полей и кнопок)


SECTION_BG     = BG_BUTTON
SECTION_BORDER = BG_BASE
SECTION_HEADER = BG_ALT




def apply_dark_theme(app):
    """Apply a modern dark-blue Fusion theme with a consistent palette and minimal QSS."""
    QApplication.setStyle("Fusion")

    pal = QPalette()
    # Core backgrounds
    pal.setColor(QPalette.Window, BG_WINDOW)
    pal.setColor(QPalette.Base, BG_BASE)
    pal.setColor(QPalette.Button, BG_BUTTON)

    # Foregrounds
    pal.setColor(QPalette.WindowText, TXT_MAIN)
    pal.setColor(QPalette.Text, TXT_MAIN)
    pal.setColor(QPalette.ButtonText, TXT_MAIN)
    pal.setColor(QPalette.ToolTipText, TXT_MAIN)
    pal.setColor(QPalette.PlaceholderText, QColor(200, 210, 220, 120))

    # Accents
    pal.setColor(QPalette.Highlight, ACCENT)
    pal.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    pal.setColor(QPalette.Link, ACCENT)
    pal.setColor(QPalette.LinkVisited, ACCENT_DARK)

    # Disabled state
    pal.setColor(QPalette.Disabled, QPalette.WindowText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.Text, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.ToolTipText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, TXT_DIM)

    pal.setColor(QPalette.Disabled, QPalette.Base, QColor(31, 31, 31))

    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor(70, 80, 100))
    pal.setColor(QPalette.Disabled, QPalette.Link, QColor(120, 160, 200))

    QApplication.setPalette(pal)





    # Minimal, crisp QSS tuned to blue accents
    app.setStyleSheet(f"""
        QToolTip {{
            border: 1px solid {BORDER_DIM.name()}; 
            background: {BG_ALT.name()};
            color: {TXT_MAIN.name()};
        }}

        /* Tabs */
        QTabWidget::pane {{ border: 1px solid {BORDER_DIM.name()}; }}
        QTabBar::tab {{
            padding: 6px 10px;
            border: 1px solid transparent;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
            background: {BG_ALT.name()};
            margin: 2px 4px 0 4px;
        }}
        QTabBar::tab:selected {{
            background: {BG_BUTTON.name()};
            border-color: {BORDER_DIM.name()};
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            border-color: {BORDER_DIM.name()};
        }}

        /* Buttons */
        QPushButton {{
            border: 1px solid {BORDER_DIM.name()};
            padding: 6px 6px;
            border-radius: 4px;
            background: {BG_BUTTON.name()};
            
        }}
        QDialogButtonBox QPushButton {{
            min-height: 15px;     
            padding: 6px 14px;    
            /* при желании: font-size: 14px; */
        }}
        
        
        QPushButton:hover {{ border-color: {ACCENT_DIM.name()}; }}
        QPushButton:pressed {{ background: {ACCENT_DARK.name()}; border-color: {ACCENT_DARK.name()}; }}
        QPushButton:disabled {{ color: {TXT_DIM.name()}; border-color: {BORDER_DIM.name()}; }}
        
       
        
        

        /* Inputs */
        QLineEdit, QPlainTextEdit, QTextEdit {{
            border: 1px solid {BORDER_DIM.name()};
            border-radius: 4px;
            padding: 4px 4px;
            background: {BG_BASE.name()};
            selection-background-color: {ACCENT.name()};
        }}
        
        QComboBox {{
            border: 1px solid {BORDER_DIM.name()};
            border-radius: 4px;
            color: {TXT_MAIN.name()};
            padding: 4px 8px;
            background: {BG_BASE.name()};
            selection-background-color: {ACCENT.name()};
        }}
        QComboBox:hover {{ border-color: {ACCENT_DIM.name()}; }}
        QComboBox:on  {{ background: {ACCENT_DARK.name()}; border-color: {ACCENT_DARK.name()}; }}
        QComboBox:disabled {{ color: {TXT_DIM.name()}; }}
        
        QComboBox::drop-down {{
            width: 18px;
            margin: 0; padding: 0;
        }}

        
        
        /* Выпадающий список */
        QComboBox QAbstractItemView {{
            background: {BG_BASE.name()};
            color: {TXT_MAIN.name()};
            selection-background-color: {ACCENT.name()};
        }}
        
        /*---------------------------------------------------------*/
        QAbstractSpinBox {{
            border: 1px solid {BORDER_DIM.name()};
            border-radius: 4px;
            background: {BG_BASE.name()};
            color: {TXT_MAIN.name()};
            padding: 4px 4px;
            selection-background-color: {ACCENT.name()};
            max-width: 30px;
        }}
        QAbstractSpinBox:hover {{ border-color: {ACCENT_DIM.name()}; }}
        QAbstractSpinBox:focus {{ border-color: {ACCENT_DIM.name()}; }}
        QAbstractSpinBox:disabled {{ color: {TXT_DIM.name()}; }}
        
        QAbstractSpinBox::up-button,
        QAbstractSpinBox::down-button {{
            width: 0px;
            border: none;
            padding: 0;
            margin: 0;
        }}

        /*---------------------------------------------------------*/
        
        QLineEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateTimeEdit:focus {{
            border-color: {ACCENT_DIM.name()};
        }}

        /* ProgressBar */
        QProgressBar {{
            border: 1px solid {BORDER_DIM.name()};
            border-radius: 4px;
            text-align: center;
            background: {BG_BASE.name()};
        }}
        QProgressBar::chunk {{ background-color: {ACCENT.name()}; }}
        
        
        /* === Sections === */
        CollapsibleSection {{
            border: 1px solid {SECTION_BG.name()};
            border-radius: 4px;
            margin: 0;
        }}
        /* Секции */
        CollapsibleSection > QToolButton#sectionHeader {{
            background: {SECTION_BG.name()};
            border-radius: 4px;
            min-height: 34px;
            padding: 4px 10px;
            text-align: left;
            font-weight: 600;
            border: 1px solid transparent;
            color: {TXT_MAIN.name()};
        }}
        
        CollapsibleSection > QToolButton#sectionHeader:hover {{ border-color: {ACCENT_DIM.name()}; }}
        CollapsibleSection > QToolButton#sectionHeader:pressed {{ background: {ACCENT_DARK.name()};  }}
        
        
        /* Loader overlay */
        QWidget#loadingOverlay {{                
            background: rgba(0,0,0,0.35);
            
        }}
        
        QWidget#loadingOverlay QLabel {{        
            background: transparent;
            border: none;
            margin: 0;
            padding: 0;
            qproperty-alignment: 'AlignCenter';  
        }}
        
        
        
        /* ==== Minimal scrollbars (global) ==== */

        /* Вертикальный */
        QScrollBar:vertical {{
            width: 10px;
            background: transparent;
            margin: 0;
        }}
        
        QScrollBar::handle:vertical {{
            background: #2c2c2c;
            border-radius: 4px;
            min-height: 24px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background: {BORDER_DIM.name()};
        }}
        /* Убираем стрелки и лишнее */
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0px;
            border: none;
            background: transparent;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        
        /* Горизонтальный */
        QScrollBar:horizontal {{
            height: 10px;
            background: transparent;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: #2c2c2c;
            border-radius: 4px;
            min-width: 24px;
        }}
        QScrollBar:horizontal:hover {{ height: 10px; }}
        QScrollBar::handle:horizontal:hover {{
            background: {BORDER_DIM.name()};
        }}
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width: 0px;
            border: none;
            background: transparent;
        }}
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
        
        
        /* GroupBox */
        QGroupBox {{
            background: transparent;             
            border: 1px solid {SECTION_BG.name()};          
            border-radius: 4px;
            margin-top: 9px;                       
            padding: 10px;                    
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;               
            subcontrol-position: top left;           
            left: 10px;                            
            padding: 0 6px;                           
            background-color: palette(window);        
            color: #E5E7EB;                          
            font-weight: 600;
        }}
        QGroupBox::title:disabled {{ color: #404040; }}
        
        
""")

    app.setStyle(app.style().objectName())
