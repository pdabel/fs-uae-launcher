import fsui
from launcher.i18n import gettext
from launcher.netplay.irc import LOBBY_CHANNEL
from launcher.netplay.irc_broadcaster import IRCBroadcaster
from launcher.netplay.netplay import Netplay
from launcher.ui.skin import Skin


class NetplayPanel(fsui.Panel):
    def __init__(self, parent, header=True):
        fsui.Panel.__init__(self, parent)
        Skin.set_background_color(self)
        self.layout = fsui.VerticalLayout()

        if header:
            hori_layout = fsui.HorizontalLayout()
            self.layout.add(hori_layout, fill=True)
            self.layout.add_spacer(0)

            label = fsui.HeadingLabel(self, gettext("Net Play"))
            hori_layout.add(label, margin=10)

            hori_layout.add_spacer(0, expand=True)

        # label = fsui.Label(self, "Netplay is currently disabled in the "
        #                          "development versions.")
        # self.layout.add(label, margin=10)
        # label = fsui.Label(self, "Please use the stable FS-UAE series for "
        #                          "netplay in the meantime.")
        # self.layout.add(label, margin=10)
        # return

        # TODO
        gettext("Nick:")
        gettext("Connect")
        gettext("Disconnect")

        hori_layout = fsui.HorizontalLayout()
        button_layout = fsui.HorizontalLayout()
        self.layout.add(hori_layout, fill=True, expand=True)
        

        ver_layout = fsui.VerticalLayout()
        hori_layout.add(ver_layout, fill=True)
        self.channel_list = fsui.ListView(self)
        self.channel_list.set_min_width(212)
        self.channel_list.on_select_item = self.on_select_channel
        ver_layout.add(self.channel_list, fill=True, expand=True, margin=10)
        self.nick_list = fsui.ListView(self)
        ver_layout.add(self.nick_list, fill=True, expand=True, margin=10)

        self.text_area = fsui.TextArea(self, font_family="monospace")
        hori_layout.add(
            self.text_area, fill=True, expand=True, margin=10, margin_left=0
        )

        input_row = fsui.HorizontalLayout()
        self.layout.add(input_row, fill=True, margin=10, margin_top=0)

        input_row.add(fsui.Label(self, gettext("Port (default: 25101)")), margin_right=5)
        self.port_field = fsui.TextField(self)
        self.port_field.set_text("25101")
        input_row.add(self.port_field, fill=False, margin_right=15)

        input_row.add(fsui.Label(self, gettext("Number of Players")), margin_right=5)
        self.player_count_field = fsui.TextField(self)
        self.player_count_field.set_text("2")
        input_row.add(self.player_count_field, fill=False)

        self.layout.add(fsui.Label(self, gettext("Netplay Server Commands")), margin=10, margin_top=10)
        self.input_field = fsui.TextField(self)
        self.input_field.activated.connect(self.on_input)
        self.layout.add(self.input_field, fill=True, margin=10, margin_top=0)
        self.layout.add(button_layout, margin=10)
        self.netplay = Netplay()
        IRCBroadcaster.add_listener(self)
        start_channel_button = StartChannelButton(self, self.netplay.irc)
        button_layout.add(start_channel_button, fill=True, margin_left=0)
        host_game_button = HostGameButton(self, self.netplay, self)
        button_layout.add(host_game_button, fill=True, margin_left=10)
        self.active_channel = LOBBY_CHANNEL

        self.input_field.focus()

    def on_destroy(self):
        print("NetplayPanel.on_destroy")
        IRCBroadcaster.remove_listener(self)
        self.netplay.disconnect()

    def on_show(self):
        # FIXME: currently disabled
        # return
        if not self.netplay.is_connected():
            self.netplay.connect()
        self.input_field.focus()

    def on_select_channel(self, index):
        # index = self.channel_list.get_index()
        # if index == 0:
        #     channel = ""
        # else:
        # assert index is not None
        if index is None:
            return
        channel = self.channel_list.get_item(index)
        self.netplay.irc.set_active_channel_name(channel)
        self.input_field.focus()

    def on_input(self):
        command = self.input_field.get_text().strip()
        if not command:
            return
        if self.netplay.handle_command(command):
            pass
        else:
            self.netplay.irc.handle_command(command)
        self.input_field.set_text("")

    def set_active_channel(self, channel):
        if channel == self.active_channel:
            return
        self.text_area.set_text("")
        # self.text_area.append_text(IRC.channel(channel).get_text())
        ch = self.netplay.irc.channel(channel)
        for i, line in enumerate(ch.lines):
            self.text_area.append_text(line, ch.colors[i])
        self.active_channel = channel
        self.update_nick_list()
        for i in range(self.channel_list.get_item_count()):
            if self.channel_list.get_item(i) == channel:
                self.channel_list.set_index(i)

    def update_channel_list(self):
        items = sorted(self.netplay.irc.channels.keys())
        # items[0] = "IRC ({0})".format(Settings.get_irc_server())
        # items[0] = Settings.get_irc_server()
        self.channel_list.set_items(items)

    def update_nick_list(self):
        items = self.netplay.irc.channel(self.active_channel).get_nick_list()
        self.nick_list.set_items(items)

    def on_irc(self, key, args):
        if key == "active_channel":
            self.set_active_channel(args["channel"])
        elif key == "nick_list":
            if args["channel"] == self.active_channel:
                self.update_nick_list()
        elif key == "channel_list":
            self.update_channel_list()
        elif key == "message":
            if args["channel"] == self.active_channel:
                self.text_area.append_text(
                    args["message"], color=args["color"]
                )
            self.window.alert()

class StartChannelButton(fsui.Button):
    def __init__(self, parent, irc):
        super().__init__(parent, gettext("Start Game Channel"))
        self.irc = irc

    def on_activated(self):
        #     #TODO: DIAGLOG BOX FOR INPUT
        self.irc.handle_command(f"/join #sensible-game")

class HostGameButton(fsui.Button):
    def __init__(self, parent, netplay, panel):
        super().__init__(parent, gettext("Host Game"))
        self.netplay = netplay
        self.panel = panel
        self.set_tooltip(gettext("Host a game on the IRC channel."))

    def on_activated(self):
        port = self.panel.port_field.get_text().strip() or "25101"
        player_count = self.panel.player_count_field.get_text().strip() or "2"
        self.netplay.handle_command(
            f"/hostgame {self.netplay.irc.client.host}:{port} {player_count}"
        )
