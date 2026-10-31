"""Modern Dark and its futuristic skins.

Every skin shares one dashboard layout and one stylesheet; only the
``ModernPalette`` tokens differ. UI code that needs a theme colour reads it
through ``palette()`` or renders a ``@token@`` template with ``render()``
instead of hard-coding hex values.
"""

from dataclasses import asdict, dataclass, replace
from pathlib import Path

from qtpy.QtGui import QColor, QFont, QFontDatabase, QPalette


@dataclass(frozen=True)
class ModernPalette:
    name: str
    label: str
    # Surfaces
    window: str
    surface: str
    raised: str
    input: str
    alt_row: str
    nav: str
    # Text
    text: str
    muted: str
    caption: str
    brand: str
    disabled_text: str
    nav_text: str
    # Accent
    accent: str
    accent_hover: str
    accent_text: str
    accent_soft: str
    icon: str
    highlight: str
    pressed: str
    # Lines
    border: str
    border_hover: str
    border_strong: str
    nav_border: str
    disabled_border: str
    hover: str
    nav_hover: str
    # Status
    success: str
    success_bg: str
    danger: str
    # Fusion palette shades
    light: str
    midlight: str
    mid: str
    dark: str
    scrollbar: str
    launch_disabled: str
    fonts: tuple = ("Noto Sans", "Segoe UI", "DejaVu Sans")
    font_size: int = 10
    radius: int = 6


MODERN = ModernPalette(
    name="modern",
    label="Modern Dark",
    window="#171923", surface="#212431", raised="#292d3e", input="#1c1f2c",
    alt_row="#252938", nav="#1c1e2b",
    text="#edf0f7", muted="#a2abc0", caption="#929db6", brand="#f5f7fc",
    disabled_text="#737e96", nav_text="#aeb8ce",
    accent="#46b7ee", accent_hover="#72d2f2", accent_text="#101d28",
    accent_soft="#73cef8", icon="#9bcce2", highlight="#254f69",
    pressed="#253e54",
    border="#3a4155", border_hover="#64718b", border_strong="#454d64",
    nav_border="#303447", disabled_border="#303648", hover="#353d52",
    nav_hover="#282d40",
    success="#69d6ae", success_bg="#173c3a", danger="#fa7979",
    light="#454c62", midlight="#353b4e", mid="#303648", dark="#11131c",
    scrollbar="#4b536c", launch_disabled="#303649",
)

# Neon magenta on near-black, with cyan secondary glow and sharp corners.
CYBERPUNK = replace(
    MODERN,
    name="cyberpunk",
    label="Neon City",
    window="#0b0a12", surface="#13111f", raised="#1c1930", input="#0f0e1a",
    alt_row="#171427", nav="#0e0c18",
    text="#f3ecff", muted="#a48fc4", caption="#8b78ab", brand="#fff0fb",
    disabled_text="#5e5479", nav_text="#b9a6d6",
    accent="#ff2bd6", accent_hover="#ff6ae4", accent_text="#1a0a18",
    accent_soft="#19e6ff", icon="#19e6ff", highlight="#5a1552",
    pressed="#3d1040",
    border="#3a2f5c", border_hover="#8a4fd6", border_strong="#4b3a78",
    nav_border="#2a2145", disabled_border="#2a2340", hover="#271f3f",
    nav_hover="#1e1833",
    success="#39ffb4", success_bg="#0f3a30", danger="#ff4f6d",
    light="#4b3f73", midlight="#302753", mid="#261f45", dark="#06050c",
    scrollbar="#5b4a8a", launch_disabled="#2a2340",
    radius=2,
)

# Sunset orange over deep violet, pink highlights, soft rounded corners.
SYNTHWAVE = replace(
    MODERN,
    name="synthwave",
    label="Synthwave Sunset",
    window="#1a1030", surface="#241744", raised="#2f1f57", input="#1f1439",
    alt_row="#29194c", nav="#160d2b",
    text="#fff1f8", muted="#c7a9e0", caption="#a98cc6", brand="#ffe9a8",
    disabled_text="#6f5c93", nav_text="#d5bdea",
    accent="#ff9f43", accent_hover="#ffb86b", accent_text="#2a1300",
    accent_soft="#ff5fa2", icon="#f6c177", highlight="#6a2a63",
    pressed="#4a2160",
    border="#45307a", border_hover="#ff5fa2", border_strong="#5a3f94",
    nav_border="#2f1f57", disabled_border="#33255a", hover="#3a2868",
    nav_hover="#2a1a4e",
    success="#6ef2c7", success_bg="#163f3a", danger="#ff6b8a",
    light="#5c4590", midlight="#3f2d6c", mid="#34265a", dark="#0f0820",
    scrollbar="#6d55a3", launch_disabled="#33255a",
    radius=10,
)

# Cyan hologram lines on a dark teal void, square edges.
HOLOGRAM = replace(
    MODERN,
    name="hologram",
    label="Holo Grid",
    window="#04111a", surface="#082030", raised="#0c2b40", input="#061a28",
    alt_row="#0a2536", nav="#031019",
    text="#d8f6ff", muted="#7fb7c9", caption="#5f9bb0", brand="#e9fdff",
    disabled_text="#3f6f80", nav_text="#9ad4e6",
    accent="#00e5ff", accent_hover="#66efff", accent_text="#002a33",
    accent_soft="#9cf7ff", icon="#00e5ff", highlight="#0b4a5c",
    pressed="#0a3c4b",
    border="#0f3b4c", border_hover="#00b8cc", border_strong="#155266",
    nav_border="#0a3040", disabled_border="#0c2e3b", hover="#0e3647",
    nav_hover="#07293a",
    success="#5dffc3", success_bg="#0b3d33", danger="#ff6a7a",
    light="#1b5c70", midlight="#123f50", mid="#0f3443", dark="#020a0f",
    scrollbar="#1f6b82", launch_disabled="#0c2e3b",
    radius=0,
)

# Green phosphor terminal, monospace, no rounding.
TERMINAL = replace(
    MODERN,
    name="terminal",
    label="Phosphor Terminal",
    window="#050a05", surface="#0a140a", raised="#102010", input="#081008",
    alt_row="#0d190d", nav="#040904",
    text="#b8ffb0", muted="#5fa85a", caption="#4e8f4a", brand="#dcffd6",
    disabled_text="#2f5c2d", nav_text="#8fdc88",
    accent="#39ff14", accent_hover="#7dff63", accent_text="#03210a",
    accent_soft="#c4ff9a", icon="#39ff14", highlight="#11401a",
    pressed="#0e3315",
    border="#1e4a1e", border_hover="#39ff14", border_strong="#2a602a",
    nav_border="#143414", disabled_border="#142a14", hover="#163016",
    nav_hover="#0f220f",
    success="#39ff14", success_bg="#0b2a0b", danger="#ff5c5c",
    light="#2a5c2a", midlight="#1c421c", mid="#163616", dark="#020402",
    scrollbar="#2f6f2f", launch_disabled="#142a14",
    fonts=("Noto Sans Mono", "DejaVu Sans Mono", "Liberation Mono",
           "Courier New"),
    radius=0,
)

SKINS = {
    skin.name: skin for skin in (MODERN, CYBERPUNK, SYNTHWAVE, HOLOGRAM, TERMINAL)
}
DEFAULT_SKIN = MODERN.name
_active = MODERN

# Kept for callers that only need Modern Dark's base colours.
BACKGROUND = MODERN.window
SURFACE = MODERN.surface
RAISED = MODERN.raised
TEXT = MODERN.text
MUTED = MODERN.muted
ACCENT = MODERN.accent


def palette(skin=None):
    """The active skin, or a named one."""
    if skin is None:
        return _active
    return SKINS.get(skin, MODERN)


def render(template, skin=None):
    """Replace ``@token@`` placeholders with palette values."""
    tokens = asdict(palette(skin))
    tokens["icons"] = (Path(__file__).parent / "res").as_posix()
    tokens["radius"] = f"{tokens['radius']}px"
    tokens["radius_small"] = f"{max(0, palette(skin).radius - 2)}px"
    for key, value in tokens.items():
        if isinstance(value, (str, int)):
            template = template.replace(f"@{key}@", str(value))
    return template


def apply_modern_theme(application, skin=DEFAULT_SKIN):
    global _active
    _active = SKINS.get(skin, MODERN)
    p = _active
    qpalette = QPalette()
    colors = {
        QPalette.Window: p.window,
        QPalette.WindowText: p.text,
        QPalette.Base: p.surface,
        QPalette.AlternateBase: p.raised,
        QPalette.Text: p.text,
        QPalette.Button: p.raised,
        QPalette.ButtonText: p.text,
        QPalette.ToolTipBase: p.raised,
        QPalette.ToolTipText: p.text,
        QPalette.Highlight: p.highlight,
        QPalette.HighlightedText: "#ffffff",
        QPalette.Link: p.accent,
        QPalette.BrightText: p.danger,
        QPalette.Light: p.light,
        QPalette.Midlight: p.midlight,
        QPalette.Mid: p.mid,
        QPalette.Dark: p.dark,
        QPalette.Shadow: p.dark,
        QPalette.PlaceholderText: p.muted,
    }
    for role, value in colors.items():
        qpalette.setColor(role, QColor(value))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        qpalette.setColor(QPalette.Disabled, role, QColor(p.disabled_text))
    application.setPalette(qpalette)
    families = QFontDatabase.families()
    for family in p.fonts:
        if family in families:
            application.setFont(QFont(family, p.font_size))
            break
    application.setStyleSheet(render(STYLESHEET))


STYLESHEET = """
    QToolTip { color: @text@; background: @raised@;
        border: 1px solid @light@; padding: 6px; }
    QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox {
        background: @input@; color: @text@;
        border: 1px solid @border@; border-radius: @radius@;
        padding: 7px 10px; selection-background-color: @highlight@;
    }
    QLineEdit:hover, QAbstractSpinBox:hover { border-color: @border_hover@; }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QAbstractSpinBox:focus {
        border-color: @accent@;
    }
    QPushButton, QToolButton { background: @raised@; color: @text@;
        border: 1px solid @border@; border-radius: @radius@;
        padding: 7px 12px; }
    QPushButton:hover, QToolButton:hover {
        background: @hover@; border-color: @border_hover@; }
    QPushButton:pressed, QToolButton:pressed { background: @pressed@; }
    QPushButton:checked, QToolButton:checked {
        background: @pressed@; border-color: @accent@; color: @accent_soft@; }
    QPushButton:focus, QToolButton:focus { border-color: @accent@; }
    QPushButton:disabled, QToolButton:disabled, QComboBox:disabled,
    QLineEdit:disabled, QAbstractSpinBox:disabled {
        background: @input@; color: @disabled_text@;
        border-color: @disabled_border@; }
    QComboBox { background: @input@; color: @text@;
        border: 1px solid @border@; border-radius: @radius@;
        padding: 7px 34px 7px 10px; }
    QComboBox:hover { border-color: @border_hover@; }
    QComboBox:focus, QComboBox:on { border-color: @accent@; }
    QComboBox::drop-down { subcontrol-origin: padding;
        subcontrol-position: top right; width: 28px; border: 0; }
    QComboBox::down-arrow { image: url(@icons@/chevron-down.svg);
        width: 12px; height: 12px; }
    QComboBox QAbstractItemView { background: @surface@; color: @text@;
        border: 1px solid @border_strong@; border-radius: @radius@;
        padding: 4px; outline: none;
        selection-background-color: @pressed@; }
    QComboBox QAbstractItemView::item { min-height: 30px;
        padding: 2px 8px; border-radius: @radius_small@; }
    QSpinBox { padding-right: 28px; }
    QSpinBox::up-button, QSpinBox::down-button {
        subcontrol-origin: border; width: 24px;
        background: transparent; border: 0; border-left: 1px solid @border@; }
    QSpinBox::up-button { subcontrol-position: top right; }
    QSpinBox::down-button { subcontrol-position: bottom right; }
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {
        background: @hover@; }
    QSpinBox::up-arrow { image: url(@icons@/chevron-up.svg);
        width: 10px; height: 10px; }
    QSpinBox::down-arrow { image: url(@icons@/chevron-down.svg);
        width: 10px; height: 10px; }
    QAbstractItemView { background: @surface@; color: @text@;
        alternate-background-color: @alt_row@; border: 0;
        selection-background-color: @highlight@;
        selection-color: #ffffff; }
    QHeaderView::section { background: @raised@; color: @muted@;
        border: 0; padding: 7px; }
    QMenu { background: @surface@; color: @text@;
        border: 1px solid @border_strong@; padding: 5px; }
    QMenu::item { padding: 8px 26px 8px 12px; border-radius: @radius_small@; }
    QMenu::item:selected { background: @highlight@; }
    QMenu::item:disabled { color: @disabled_text@; }
    QMenu::separator { height: 1px; background: @border@; margin: 4px; }
    QScrollBar:vertical { background: @input@; width: 10px; margin: 0; }
    QScrollBar::handle:vertical { background: @scrollbar@;
        min-height: 28px; border-radius: @radius_small@; }
    QScrollBar:horizontal { background: @input@; height: 10px; margin: 0; }
    QScrollBar::handle:horizontal { background: @scrollbar@;
        min-width: 28px; border-radius: @radius_small@; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QCheckBox, QRadioButton { color: @text@; spacing: 7px; }
    QCheckBox:disabled, QRadioButton:disabled { color: @disabled_text@; }
    QCheckBox::indicator, QRadioButton::indicator {
        width: 16px; height: 16px; background: @input@;
        border: 1px solid @border_hover@; }
    QCheckBox::indicator { border-radius: @radius_small@; }
    QRadioButton::indicator { border-radius: 9px; }
    QCheckBox::indicator:hover, QRadioButton::indicator:hover,
    QCheckBox::indicator:focus, QRadioButton::indicator:focus {
        border-color: @accent@; }
    QCheckBox::indicator:checked { background: @accent@;
        border-color: @accent@; image: url(@icons@/check.svg); }
    QCheckBox::indicator:indeterminate { background: @accent@;
        border: 5px solid @input@; }
    QRadioButton::indicator:checked { background: @accent@;
        border: 4px solid @input@; }
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
        border-color: @disabled_border@; }
    QCheckBox::indicator:checked:disabled,
    QRadioButton::indicator:checked:disabled { background: @border_hover@; }
    QProgressBar { background: @raised@; border: 0;
        color: @text@; border-radius: @radius_small@; text-align: center; }
    QProgressBar::chunk { background: @accent@; border-radius: @radius_small@; }
"""
