import fsui
from fsui.qt import QApplication, QScrollArea, QVBoxLayout
from launcher.i18n import gettext
from launcher.netplay.lobby_browser_panel import LobbyBrowserPanel
from launcher.netplay.netplay import Netplay


class NetplayPage(fsui.Panel):
    """The Net Play tab: the lobby browser, and the game this launcher is
    in or hosting."""

    def __init__(self, parent):
        super().__init__(parent)
        self.widget().setObjectName("netplayPage")
        self.netplay = Netplay()
        layout = QVBoxLayout(self.widget())
        layout.setContentsMargins(0, 0, 0, 0)
        self.browser_panel = LobbyBrowserPanel(
            self.netplay,
            open_settings=self._open_netplay_settings,
            show_info=self._show_info,
        )
        self.browser_area = QScrollArea()
        self.browser_area.setWidgetResizable(True)
        self.browser_area.setWidget(self.browser_panel)
        layout.addWidget(self.browser_area)

    def _open_netplay_settings(self):
        from launcher.settings.settings_dialog import SettingsDialog

        dialog = SettingsDialog.open(self.get_window())
        dialog.set_page_by_title(gettext("Net Play"))

    def _show_info(self):
        from launcher.ui.InfoDialog import InfoDialog

        for widget in QApplication.topLevelWidgets():
            if widget.windowTitle() == "Netplay Info":
                widget.raise_()
                widget.activateWindow()
                return
        InfoDialog(self).show()

    def on_show(self):
        if not self.netplay.is_connected():
            self.netplay.connect()

    def shutdown(self):
        self.browser_panel.shutdown()
        self.netplay.disconnect()
