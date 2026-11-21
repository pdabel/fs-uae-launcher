import fsui
from fsui.extra.iconheader import IconHeader
from launcher.ui.skin import LauncherTheme
from launcher.ui.widgets import CloseButton

class InfoDialog(fsui.Window):
    def __init__(self, parent):
        app_name = "Netplay Info"
        title = f"{app_name}"
        super().__init__(parent, title, minimizable=False, maximizable=False)
        self.theme = LauncherTheme.get()
        self.layout = fsui.VerticalLayout()
        self.layout.set_padding(20)

        self.icon_header = IconHeader(
            self,
            fsui.Icon("fs-uae-launcher", "pkg:launcher"),
            f"{app_name}",
            "Copyright © 2012-2017 Frode Solheim",
        )
        self.layout.add(self.icon_header, fill=True, margin_bottom=20)

        self.text_area = fsui.TextArea(
            self, info_message, read_only=True, font_family="monospace"
        )
        self.text_area.scroll_to_start()
        self.text_area.set_min_width(760)
        self.text_area.set_min_height(340)
        self.layout.add(self.text_area, fill=True, expand=True)

        CloseButton.add_to_layout(self, self.layout, margin_top=20)


info_message = """\n
How to Use Netplay:

1. Add the lobby servers you play on in Settings > Net Play. The Net Play
   tab lists every game waiting for players on them.
2. To play a listed game, press its 'Join'. For a game that isn't listed,
   use 'Join by ID...' with the ID its host gave you.
3. To host, choose the game and its settings, then press 'Host game'.
   Pick a server, or This computer (set the address players reach you at
   in Settings > Net Play, and forward its port to this computer).
4. Every player's launcher takes the game's config from the lobby. The
   game view shows each player as ready, missing files, or config
   differs. If you are missing a file, add it and press 'Re-check'.
5. Once every player has joined and is ready, FS-UAE starts for everyone.
   Nobody presses Start.

Games hosted with IRC commands in a game channel still work as before:
the host presses 'Start Game' once every player is ready.

If required, you can use the netplay command box to enter manual IRC or netplay commands.

You can also use IRC commands directly in the command box as follows:
(Replace text within <> as appropriate)

Create a game channel (make sure the -game is appended):
/join #<game-name>-game
Once in the channel, host a game using the FQDN to allow players to either
use public DNS resolution or a static host file entry.
To host the game here for a specific number of players (in this case 2):
/hostgame <host.domain.com>:<port> <players>
Or create it on a netplay server (lobby) elsewhere:
/startgame <lobby.domain.com>[:<port>] <players>

Players join automatically. If an announcement was missed:
/joingame <host>:<port> <game-id>

Other commands:

/recheck        apply the game's config again
/reset          leave the game (the host ends it)
/resetconfig    reset your config (the host's reaches every player)
/set <key> <value>

More info @ https://fs-uae.net/launcher-net-play
"""
