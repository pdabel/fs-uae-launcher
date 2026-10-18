from pathlib import Path

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
            border: 1px solid #3a4155; border-radius: 6px;
            padding: 7px 10px; selection-background-color: #254f69;
        }
        QLineEdit:hover, QAbstractSpinBox:hover { border-color: #64718b; }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QAbstractSpinBox:focus {
            border-color: #46b7ee;
        }
        QPushButton, QToolButton { background: #292d3e; color: #edf0f7;
            border: 1px solid #3a4155; border-radius: 6px;
            padding: 7px 12px; }
        QPushButton:hover, QToolButton:hover {
            background: #353d52; border-color: #64718b; }
        QPushButton:pressed, QToolButton:pressed { background: #253e54; }
        QPushButton:checked, QToolButton:checked {
            background: #253e54; border-color: #46b7ee; color: #73cef8; }
        QPushButton:focus, QToolButton:focus { border-color: #46b7ee; }
        QPushButton:disabled, QToolButton:disabled, QComboBox:disabled,
        QLineEdit:disabled, QAbstractSpinBox:disabled {
            background: #1c1f2c; color: #737e96; border-color: #303648; }
        QComboBox { background: #1c1f2c; color: #edf0f7;
            border: 1px solid #3a4155; border-radius: 6px;
            padding: 7px 34px 7px 10px; }
        QComboBox:hover { border-color: #64718b; }
        QComboBox:focus, QComboBox:on { border-color: #46b7ee; }
        QComboBox::drop-down { subcontrol-origin: padding;
            subcontrol-position: top right; width: 28px; border: 0; }
        QComboBox::down-arrow { image: url(@ICONS@/chevron-down.svg);
            width: 12px; height: 12px; }
        QComboBox QAbstractItemView { background: #212431; color: #edf0f7;
            border: 1px solid #454d64; border-radius: 6px;
            padding: 4px; outline: none;
            selection-background-color: #253e54; }
        QComboBox QAbstractItemView::item { min-height: 30px;
            padding: 2px 8px; border-radius: 4px; }
        QSpinBox { padding-right: 28px; }
        QSpinBox::up-button, QSpinBox::down-button {
            subcontrol-origin: border; width: 24px;
            background: transparent; border: 0; border-left: 1px solid #3a4155; }
        QSpinBox::up-button { subcontrol-position: top right; }
        QSpinBox::down-button { subcontrol-position: bottom right; }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background: #353d52; }
        QSpinBox::up-arrow { image: url(@ICONS@/chevron-up.svg);
            width: 10px; height: 10px; }
        QSpinBox::down-arrow { image: url(@ICONS@/chevron-down.svg);
            width: 10px; height: 10px; }
        QAbstractItemView { background: #212431; color: #edf0f7;
            alternate-background-color: #252938; border: 0;
            selection-background-color: #254f69;
            selection-color: #ffffff; }
        QHeaderView::section { background: #292d3e; color: #a2abc0;
            border: 0; padding: 7px; }
        QMenu { background: #212431; color: #edf0f7;
            border: 1px solid #454d64; padding: 5px; }
        QMenu::item { padding: 8px 26px 8px 12px; border-radius: 4px; }
        QMenu::item:selected { background: #254f69; }
        QMenu::item:disabled { color: #737e96; }
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
        QCheckBox:disabled, QRadioButton:disabled { color: #737e96; }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 16px; height: 16px; background: #1c1f2c;
            border: 1px solid #64718b; }
        QCheckBox::indicator { border-radius: 4px; }
        QRadioButton::indicator { border-radius: 9px; }
        QCheckBox::indicator:hover, QRadioButton::indicator:hover,
        QCheckBox::indicator:focus, QRadioButton::indicator:focus {
            border-color: #46b7ee; }
        QCheckBox::indicator:checked { background: #46b7ee;
            border-color: #46b7ee; image: url(@ICONS@/check.svg); }
        QCheckBox::indicator:indeterminate { background: #46b7ee;
            border: 5px solid #1c1f2c; }
        QRadioButton::indicator:checked { background: #46b7ee;
            border: 4px solid #1c1f2c; }
        QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
            border-color: #303648; }
        QCheckBox::indicator:checked:disabled,
        QRadioButton::indicator:checked:disabled { background: #64718b; }
        QProgressBar { background: #292d3e; border: 0;
            color: #edf0f7; border-radius: 4px; text-align: center; }
        QProgressBar::chunk { background: #46b7ee; border-radius: 4px; }
    """.replace("@ICONS@", (Path(__file__).parent / "res").as_posix()))