from qtpy.QtGui import QColor, QFont, QFontDatabase, QPalette


BACKGROUND = "#171923"
SURFACE = "#212431"
RAISED = "#292d3e"
TEXT = "#edf0f7"
MUTED = "#a2abc0"
ACCENT = "#46b7ee"


def apply_modern_theme(application):
    palette = QPalette()
    colors = {
        QPalette.Window: BACKGROUND,
        QPalette.WindowText: TEXT,
        QPalette.Base: SURFACE,
        QPalette.AlternateBase: RAISED,
        QPalette.Text: TEXT,
        QPalette.Button: RAISED,
        QPalette.ButtonText: TEXT,
        QPalette.ToolTipBase: RAISED,
        QPalette.ToolTipText: TEXT,
        QPalette.Highlight: "#254f69",
        QPalette.HighlightedText: "#ffffff",
        QPalette.Link: ACCENT,
        QPalette.BrightText: "#fa7979",
        QPalette.Light: "#454c62",
        QPalette.Midlight: "#353b4e",
        QPalette.Mid: "#303648",
        QPalette.Dark: "#11131c",
        QPalette.Shadow: "#11131c",
        QPalette.PlaceholderText: MUTED,
    }
    for role, value in colors.items():
        palette.setColor(role, QColor(value))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor("#737e96"))
    application.setPalette(palette)
    families = QFontDatabase.families()
    for family in ("Noto Sans", "Segoe UI", "DejaVu Sans"):
        if family in families:
            application.setFont(QFont(family, 10))
            break
    application.setStyleSheet("""
        QToolTip { color: #edf0f7; background: #292d3e;
            border: 1px solid #454c62; padding: 6px; }
        QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox {
            background: #1c1f2c; color: #edf0f7;
            border: 1px solid #3a4155; border-radius: 4px;
            padding: 5px 7px; selection-background-color: #254f69;
        }
        QLineEdit:focus, QTextEdit:focus, QAbstractSpinBox:focus {
            border-color: #46b7ee;
        }
        QPushButton { background: #303649; color: #edf0f7;
            border: 1px solid #454d64; border-radius: 4px;
            padding: 6px 10px; }
        QPushButton:hover { background: #3b445d; border-color: #6d85a2; }
        QPushButton:pressed { background: #254f69; }
        QPushButton:disabled { color: #737e96; border-color: #303648; }
        QComboBox { background: #292d3e; color: #edf0f7;
            border: 1px solid #454d64; border-radius: 4px;
            padding: 5px 7px; }
        QComboBox QAbstractItemView { background: #212431; color: #edf0f7;
            selection-background-color: #254f69; }
        QAbstractItemView { background: #212431; color: #edf0f7;
            alternate-background-color: #252938; border: 0;
            selection-background-color: #254f69;
            selection-color: #ffffff; }
        QHeaderView::section { background: #292d3e; color: #a2abc0;
            border: 0; padding: 7px; }
        QMenu { background: #212431; color: #edf0f7;
            border: 1px solid #454d64; padding: 5px; }
        QMenu::item { padding: 8px 26px 8px 12px; }
        QMenu::item:selected { background: #254f69; }
        QMenu::separator { height: 1px; background: #3a4155; margin: 4px; }
        QScrollBar:vertical { background: #1c1f2c; width: 10px; margin: 0; }
        QScrollBar::handle:vertical { background: #4b536c;
            min-height: 28px; border-radius: 4px; }
        QScrollBar:horizontal { background: #1c1f2c; height: 10px; margin: 0; }
        QScrollBar::handle:horizontal { background: #4b536c;
            min-width: 28px; border-radius: 4px; }
        QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
        QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        QCheckBox, QRadioButton { color: #edf0f7; spacing: 7px; }
        QProgressBar { background: #292d3e; border: 0;
            color: #edf0f7; border-radius: 4px; text-align: center; }
        QProgressBar::chunk { background: #46b7ee; border-radius: 4px; }
    """)