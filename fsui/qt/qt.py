import functools
import os
import sys
import weakref

import fsbc.application
import fsbc.desktop
import fsboot
from fsbc.settings import Settings


def configure_qt_environment():
    os.environ.setdefault("QT_API", "pyside6")
    desktops = os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    if sys.platform.startswith("linux") and "GNOME" in desktops:
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")


configure_qt_environment()

# noinspection PyUnresolvedReferences, PyPackageRequirements
from qtpy.QtCore import *

# noinspection PyUnresolvedReferences, PyPackageRequirements
from qtpy.QtGui import *

# noinspection PyUnresolvedReferences, PyPackageRequirements
from qtpy.QtWidgets import *

# noinspection PyUnresolvedReferences, PyPackageRequirements
from qtpy.QtCore import Signal

# noinspection PyUnresolvedReferences, PyPackageRequirements
from qtpy.QtCore import Signal as QSignal

# noinspection PyUnresolvedReferences, PyPackageRequirements
from qtpy.QtOpenGL import *
from qtpy.QtOpenGLWidgets import *

from fsgs.option import Option


def open_url_in_browser(url):
    print("[QT] open_url_in_browser", url)
    # noinspection PyCallByClass,PyTypeChecker,PyArgumentList
    QDesktopServices.openUrl(QUrl(url))


class DesktopScreens:
    def screenCount(self):
        return len(QGuiApplication.screens())

    def screenGeometry(self, index):
        return QGuiApplication.screens()[index].geometry()


class QtBaseApplication(QApplication):
    def desktop(self):
        return DesktopScreens()


@functools.lru_cache()
def init_qt():
    fsbc.desktop.set_open_url_in_browser_function(open_url_in_browser)
    qapplication = QtBaseApplication(sys.argv)
    initialize_qt_style(qapplication)
    return qapplication


def initialize_qt_style(qapplication):
    launcher_theme = Settings.instance().get(Option.LAUNCHER_THEME)
    for argument in sys.argv[1:]:
        if argument.startswith("--launcher-theme="):
            launcher_theme = argument.split("=", 1)[1]
    if launcher_theme and resolve_launcher_theme(launcher_theme) is None:
        Settings.instance().set(Option.LAUNCHER_THEME, "fusion-plain")
    apply_launcher_theme(
        qapplication,
        launcher_theme,
        Settings.instance().get("launcher_font_size"),
    )


# Widgets that render their own stylesheets register here and are re-styled
# after apply_launcher_theme replaces the application palette and QSS.
class ThemeListeners:
    def __init__(self):
        self._refs = []

    def connect(self, method):
        self._refs.append(weakref.WeakMethod(method))

    def disconnect(self, method):
        self._refs = [
            ref for ref in self._refs
            if ref() is not None and ref() != method
        ]

    def notify(self):
        alive = []
        for ref in self._refs:
            callback = ref()
            if callback is None:
                continue
            try:
                callback()
            except RuntimeError:
                # The underlying Qt object is gone; drop the listener.
                continue
            alive.append(ref)
        self._refs = alive


theme_applied = ThemeListeners()


def resolve_launcher_theme(launcher_theme):
    """Map a launcher_theme setting to (variant, skin); None if unknown."""
    from fsui.qt.modern_theme import SKINS

    themes = {
        "fusion-plain": ("plain", ""),
        "fusion-windows311": ("windows311", ""),
        "fusion-workbench": ("workbench", ""),
    }
    for skin in SKINS:
        themes["fusion-" + skin] = ("modern", skin)
    return themes.get(launcher_theme or "fusion-modern")


def apply_launcher_theme(qapplication, launcher_theme, font_size=""):
    """Apply a theme to a running application; unknown names mean Fusion."""
    fusion_variant, skin = resolve_launcher_theme(launcher_theme) or (
        "plain", ""
    )
    qapplication.setStyleSheet("")
    qapplication.setStyle(QStyleFactory.create("Fusion"))
    qapplication.setPalette(qapplication.style().standardPalette())
    qapplication.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
    if fusion_variant == "modern":
        from fsui.qt.modern_theme import apply_modern_theme

        apply_modern_theme(qapplication, skin)
    elif fusion_variant in ("windows311", "workbench"):
        from fsui.qt.retro_theme import apply_retro_theme

        apply_retro_theme(qapplication, fusion_variant)
    try:
        launcher_font_size = int(font_size)
    except (TypeError, ValueError):
        launcher_font_size = 0
    if launcher_font_size:
        font = qapplication.font()
        font.setPointSize(launcher_font_size)
        qapplication.setFont(font)

    import fsui

    fsui.theme = "fusion"
    fsui.theme_variant = fusion_variant
    fsui.theme_skin = skin
    theme_applied.notify()
