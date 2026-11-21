import fsui
from launcher.i18n import gettext
from launcher.settings.lobby_servers_group import LobbyServersGroup
from launcher.settings.settings_page import SettingsPage


class NetplaySettingsPage(SettingsPage):
    def __init__(self, parent):
        super().__init__(parent)
        icon = fsui.Icon("netplay-settings", "pkg:workspace")
        gettext("Net Play Settings")
        title = gettext("Net Play")
        subtitle = ""
        self.add_header(icon, title, subtitle)

        self.add_option("netplay_name")
        self.lobby_servers_group = LobbyServersGroup(self)
        self.layout.add(
            self.lobby_servers_group,
            fill=True,
            margin_top=10,
            margin_bottom=10,
        )

        self.add_section(gettext("Hosting on this computer"))
        self.add_option("netplay_public_address")
        self.add_option("netplay_host_port")
        self.layout.add(
            fsui.Label(
                self, gettext("Forward this TCP port to this computer.")
            ),
            margin_bottom=10,
        )

        self.add_section(gettext("IRC"))
        self.add_option("netplay_tag")
        self.add_option("irc_server")
