import functools
import os
import sys

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
    themes = {
        "fusion-modern": "modern",
        "fusion-plain": "plain",
        "fusion-windows311": "windows311",
        "fusion-workbench": "workbench",
    }
    launcher_theme = Settings.instance().get(Option.LAUNCHER_THEME)
    for argument in sys.argv[1:]:
        if argument.startswith("--launcher-theme="):
            launcher_theme = argument.split("=", 1)[1]
    if launcher_theme and launcher_theme not in themes:
        Settings.instance().set(Option.LAUNCHER_THEME, "fusion-plain")
    fusion_variant = themes.get(launcher_theme or "fusion-modern", "plain")
    qapplication.setStyleSheet("")
    qapplication.setStyle(QStyleFactory.create("Fusion"))
    qapplication.setPalette(qapplication.style().standardPalette())
    qapplication.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
    if fusion_variant == "modern":
        from fsui.qt.modern_theme import apply_modern_theme

        apply_modern_theme(qapplication)
    elif fusion_variant in ("windows311", "workbench"):
        from fsui.qt.retro_theme import apply_retro_theme

        apply_retro_theme(qapplication, fusion_variant)
    try:
        launcher_font_size = int(Settings.instance().get("launcher_font_size"))
    except ValueError:
        launcher_font_size = 0
    if launcher_font_size:
        font = qapplication.font()
        font.setPointSize(launcher_font_size)
        qapplication.setFont(font)

    import fsui

    fsui.theme = "fusion"
    fsui.theme_variant = fusion_variant
