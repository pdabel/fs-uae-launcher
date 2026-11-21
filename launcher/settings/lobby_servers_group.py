import fsui
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.netplay.lobby_servers import (
    add_server,
    remove_server,
    split_servers,
)
from launcher.netplay.text_input_dialog import SimpleTextInputDialog
from launcher.option import Option
from launcher.ui.IconButton import IconButton
from fsbc.util import unused


class LobbyServersGroup(fsui.Group):
    """The netplay_servers list, added to and removed from like the scan
    paths list."""

    def __init__(self, parent):
        fsui.Group.__init__(self, parent)
        self.layout = fsui.VerticalLayout()

        self.layout.add(fsui.Label(self, gettext("Lobby servers")))
        self.layout.add_spacer(6)

        row = fsui.HorizontalLayout()
        self.layout.add(row, fill=True, expand=True)

        self.list_view = fsui.ListView(self)
        self.list_view.set_min_height(100)
        row.add(self.list_view, expand=True, fill=True)
        row.add_spacer(10)

        buttons = fsui.VerticalLayout()
        row.add(buttons, fill=True)

        add_button = IconButton(self, "add_button.png")
        add_button.set_tooltip(gettext("Add Lobby Server"))
        add_button.activated.connect(self.on_add_button)
        buttons.add(add_button)
        buttons.add_spacer(10)

        self.remove_button = IconButton(self, "remove_button.png")
        self.remove_button.set_tooltip(gettext("Remove Lobby Server"))
        self.remove_button.disable()
        self.remove_button.activated.connect(self.on_remove_button)
        buttons.add(self.remove_button)

        self.layout.add_spacer(6)
        self.layout.add(
            fsui.Label(
                self,
                gettext(
                    "Connected to when the Net Play tab opens. "
                    "Port defaults to 25101."
                ),
            )
        )

        self.repopulate_list()
        self.list_view.on_select_item = self.on_select_item
        LauncherSettings.add_listener(self)

    def on_destroy(self):
        LauncherSettings.remove_listener(self)

    def on_setting(self, key, value):
        unused(value)
        if key == Option.NETPLAY_SERVERS:
            self.repopulate_list()

    def on_select_item(self, index):
        unused(index)
        self.remove_button.enable()

    def repopulate_list(self):
        self.list_view.set_items(
            split_servers(LauncherSettings.get(Option.NETPLAY_SERVERS))
        )
        self.remove_button.disable()

    def on_add_button(self):
        text = SimpleTextInputDialog.get_text(
            self.get_window(),
            gettext("Add Lobby Server"),
            gettext("Server (host or host:port):"),
            default_text="",
        )
        if not text or not text.strip():
            return
        try:
            value = add_server(
                LauncherSettings.get(Option.NETPLAY_SERVERS), text
            )
        except ValueError as e:
            fsui.show_error(str(e), gettext("Add Lobby Server"))
            return
        LauncherSettings.set(Option.NETPLAY_SERVERS, value)

    def on_remove_button(self):
        index = self.list_view.get_index()
        if index is None:
            return
        LauncherSettings.set(
            Option.NETPLAY_SERVERS,
            remove_server(
                LauncherSettings.get(Option.NETPLAY_SERVERS),
                self.list_view.get_item(index),
            ),
        )
