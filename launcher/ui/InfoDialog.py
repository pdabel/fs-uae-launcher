import fsgs
import fsui
from fsui.extra.iconheader import IconHeader
from fsbc.application import app
from launcher.i18n import gettext
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

1. Join or create a game channel using the 'Join Game Channel' button.
2. If you are hosting, enter the port and number of players, choose the
   game and its settings, and use the 'Host Game' button.
3. Everyone else's launcher joins the game and takes its config from the
   netplay server automatically. The game list under the channel shows
   each player as ready, missing files, or config differs.
4. If you are missing a file, add it and press 'Re-check'.
5. Once every player is ready, the host presses 'Start Game', and FS-UAE
   starts for everyone.

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
