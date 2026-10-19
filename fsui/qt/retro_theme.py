from pathlib import Path

from qtpy.QtGui import QColor, QFont, QFontDatabase, QPalette


def apply_retro_theme(application, variant):
    workbench = variant == "workbench"
    colors = {
        "window": "#0055aa" if workbench else "#c0c0c0",
        "window_text": "#ffffff" if workbench else "#000000",
        "base": "#ffffff",
        "text": "#0055aa" if workbench else "#000000",
        "button": "#ffffff" if workbench else "#c0c0c0",
        "highlight": "#ff8800" if workbench else "#000080",
        "selected_text": "#000000" if workbench else "#ffffff",
        "light": "#ffffff",
        "shadow": "#000000" if workbench else "#404040",
        "disabled": "#808080",
    }
    palette = QPalette()
    for role, key in (
        (QPalette.Window, "window"),
        (QPalette.WindowText, "window_text"),
        (QPalette.Base, "base"),
        (QPalette.AlternateBase, "button"),
        (QPalette.Text, "text"),
        (QPalette.Button, "button"),
        (QPalette.ButtonText, "text"),
        (QPalette.Highlight, "highlight"),
        (QPalette.HighlightedText, "selected_text"),
        (QPalette.ToolTipBase, "base"),
        (QPalette.ToolTipText, "text"),
        (QPalette.Link, "text"),
        (QPalette.Light, "light"),
        (QPalette.Midlight, "button"),
        (QPalette.Mid, "disabled"),
        (QPalette.Dark, "shadow"),
        (QPalette.Shadow, "shadow"),
        (QPalette.PlaceholderText, "disabled"),
    ):
        palette.setColor(role, QColor(colors[key]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(colors["disabled"]))
    application.setPalette(palette)
    families = QFontDatabase.families()
    candidates = (
        ("Liberation Mono", "DejaVu Sans Mono", "Courier New") if workbench
        else ("Liberation Sans", "DejaVu Sans", "Tahoma")
    )
    for family in candidates:
        if family in families:
            font = QFont(family, 10)
            if workbench:
                font.setStretch(QFont.SemiCondensed)
            application.setFont(font)
            break
    stylesheet = """
        QToolTip { background: @base@; color: @text@;
            border: 1px solid @shadow@; padding: 4px; }
        QPushButton, QToolButton, QComboBox {
            background: @button@; color: @text@; border-radius: 0;
            border: 2px solid; border-top-color: @light@;
            border-left-color: @light@; border-right-color: @shadow@;
            border-bottom-color: @shadow@; padding: 4px 8px; }
        QPushButton:pressed, QToolButton:pressed,
        QPushButton:checked, QToolButton:checked {
            border-top-color: @shadow@; border-left-color: @shadow@;
            border-right-color: @light@; border-bottom-color: @light@;
            background: @highlight@; color: @selected_text@; }
        QPushButton:focus, QToolButton:focus, QComboBox:focus {
            outline: 1px dotted @text@; }
        QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox {
            background: @base@; color: @text@; border-radius: 0;
            border: 2px solid; border-top-color: @shadow@;
            border-left-color: @shadow@; border-right-color: @light@;
            border-bottom-color: @light@; padding: 3px 5px;
            selection-background-color: @highlight@;
            selection-color: @selected_text@; }
        QComboBox { padding-right: 24px; }
        QComboBox::drop-down { width: 20px; border: 0;
            border-left: 1px solid @shadow@; background: @button@; }
        QComboBox::down-arrow { image: url(@icons@/retro-chevron.svg);
            width: 10px; height: 10px; }
        QAbstractItemView { background: @base@; color: @text@;
            alternate-background-color: @button@;
            selection-background-color: @highlight@;
            selection-color: @selected_text@; }
        QHeaderView::section { background: @button@; color: @text@;
            border: 1px solid @shadow@; padding: 4px; }
        QMenu { background: @button@; color: @text@;
            border: 2px outset @light@; padding: 2px; }
        QMenu::item { padding: 4px 24px 4px 8px; }
        QMenu::item:selected { background: @highlight@; color: @selected_text@; }
        QMenu::separator { height: 1px; background: @shadow@; margin: 3px; }
        QCheckBox, QRadioButton { spacing: 5px; }
        QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; }
        QPushButton:disabled, QToolButton:disabled, QComboBox:disabled,
        QLineEdit:disabled, QAbstractSpinBox:disabled, QMenu::item:disabled {
            color: @disabled@; }
        QScrollBar { background: @button@; border: 1px solid @shadow@; }
        QScrollBar::handle { background: @button@;
            border: 2px outset @light@; min-width: 16px; min-height: 16px; }
        QProgressBar { background: @base@; color: @text@;
            border: 1px solid @shadow@; border-radius: 0; text-align: center; }
        QProgressBar::chunk { background: @highlight@; }
    """
    if workbench:
        stylesheet += """
            QPushButton, QToolButton, QComboBox {
                border: 2px solid #000000; }
            QPushButton:pressed, QToolButton:pressed,
            QPushButton:checked, QToolButton:checked {
                background: #ff8800; color: #000000; }
            QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox {
                border: 2px solid #000000; }
            QScrollBar::handle { background: #ffffff; border: 1px solid #000000; }
        """
    for key, value in colors.items():
        stylesheet = stylesheet.replace("@" + key + "@", value)
    stylesheet = stylesheet.replace("@icons@", (Path(__file__).parent / "res").as_posix())
    application.setStyleSheet(stylesheet)