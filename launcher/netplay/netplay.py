import threading
import traceback

from fsgs.context import fsgs
from .config_apply import apply_document
from .connection_tester import ConnectionTester
from .irc import IRC, is_game_channel
from .irc_broadcaster import IRCBroadcaster
from .irc_color import IRCColor
from .lobby_client import LobbyClient
from .session import NetplaySession
from ..launcher_config import LauncherConfig
from ..server.Server import PortInUseError, Server, ServerError


# The lobby's port, for /startgame and /hostgame alike, so a host forwards
# the same single port however they host.
HOST_PORT = 25101

# The one protocol line left on IRC: an op's launcher announces the lobby
# game it created, and players' launchers join it. Everything else — the
# config, who is ready, the start — is held by the lobby. See "Future: the
# session owns the config" in docs/netplay-go-server-design.md.
SESSION_ANNOUNCE = "__session"

# The lobby's limit on a player's tag; IRC nicks are normally shorter.
MAX_TAG_LENGTH = 32


def call_after(function, *args):
    """Run function on the UI thread. fsui is imported late, and the two
    helpers are module functions, so tests can run Netplay without Qt."""
    import fsui

    fsui.call_after(function, *args)


def call_later(duration_ms, function):
    import fsui

    fsui.call_later(duration_ms, function)


def format_lobby(host, port):
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}"


def parse_lobby(text, default_port=HOST_PORT):
    """host[:port] or [v6]:port -> (host, port)."""
    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    elif text.count(":") == 1:
        host, port = text.split(":")
    else:
        host, port = text, ""
    return host, int(port) if port else default_port


class Netplay:
    _current = None

    @classmethod
    def current(cls):
        if cls._current:
            return cls._current
        return None

    def __init__(self, parent=None):
        self.enabled = False
        self.game_channel = ""
        self.connection_tester = None
        self.players = {}
        self.irc = IRC()
        self.parent = parent
        self.game_window = None
        # The lobby game this launcher is in, and where to announce it from
        # when hosting.
        self.session = None
        self.session_lobby = None
        # Bumped whenever the session ends or is replaced, so a join still
        # in flight can tell it was overtaken; and that join's game id.
        self.session_generation = 0
        self.joining = None
        # Whether the session's game is in this launcher's /hostgame
        # lobby, and whether a game was left running there: then the
        # lobby stays up for it, as nothing follows it to say when it ends.
        self.session_hosted = False
        self.hosted_game_left_running = False
        # Called with the session (or None) whenever it changes.
        self.session_listeners = []

        LauncherConfig.add_listener(self)
        IRCBroadcaster.add_listener(self)

        Netplay._current = self

    def connect(self):
        self.enabled = True
        self.irc.connect()
        if self.connection_tester is None:
            self.connection_tester = ConnectionTester()

    def disconnect(self):
        self.end_session()
        if self.game_window is not None:
            self.game_window.close()
            self.game_window = None
        if Netplay._current == self:
            Netplay._current = None

        self.enabled = False
        self.irc.stop()

        LauncherConfig.remove_listener(self)
        IRCBroadcaster.remove_listener(self)

    def is_connected(self):
        return self.enabled

    def player(self, nick):
        try:
            return self.players[nick]
        except Exception:
            from .player import Player

            self.players[nick] = Player(nick)
            return self.players[nick]

    def remove_player(self, nick):
        self.players.pop(nick, None)

    def is_op(self):
        return self.irc.channel(self.game_channel).is_op(self.irc.my_nick)

    # --- The lobby game -------------------------------------------------

    def start_netplay_game(self):
        """The Start Game button: the host asks the lobby to start."""
        if self.session is None:
            self.game_warning(
                "no game yet: an operator needs to use /startgame or "
                "/hostgame first"
            )
            return
        self.session.start_game()

    def begin_session(self, client, game_id, slot, player_token, **host):
        """Follow a lobby game; host passes host_token and sync_keys."""
        self.end_session()
        self.session = NetplaySession(
            client,
            game_id,
            slot,
            player_token,
            apply=apply_document,
            local_value=LauncherConfig.get,
            launch=self.launch_session_game,
            dispatch=call_after,
            later=call_later,
            on_change=self.on_session_change,
            on_message=self.session_message,
            **host,
        )
        self.session.start()
        self.notify_session()

    def end_session(self):
        """Leave the current game. One that hasn't started is ended — by a
        host, for everyone — along with the /hostgame lobby it was made
        in. A running game carries on, and its lobby with it: it belongs
        to the players' FS-UAE now (see NetplaySession.leave)."""
        session, self.session = self.session, None
        self.session_lobby = None
        self.session_generation += 1
        self.joining = None
        if session is not None:
            if self.session_hosted and session.started:
                self.hosted_game_left_running = True
            self.session_hosted = False
            session.leave()
            self.release_hosted_server()
            self.notify_session()

    def on_session_change(self, session):
        if session is not self.session:
            return
        if session.ended:
            self.session = None
            self.session_lobby = None
            self.session_hosted = False
            self.release_hosted_server()
            if not session.launched:
                self.reset_netplay_config()
        self.notify_session(session)

    def notify_session(self, session=None):
        for listener in list(self.session_listeners):
            listener(session or self.session)

    def session_message(self, text, warning=False):
        if warning:
            self.game_warning(text)
        else:
            self.game_info(text)

    def stop_hosted_server(self):
        if self.game_window is not None:
            self.game_window.stop_server()

    def release_hosted_server(self):
        """Stop the /hostgame lobby, unless a game left running is in it."""
        if not self.hosted_game_left_running:
            self.stop_hosted_server()

    def running_hosted_server(self):
        server = getattr(self.game_window, "server", None)
        if server is None or server.process is None:
            return None
        if server.process.poll() is not None:
            return None
        return server

    def launch_session_game(self, snapshot):
        listed = snapshot["config"].get("__netplay_addresses", "")
        addresses = [a.strip() for a in listed.split(",") if a.strip()]
        if LauncherConfig.get("__netplay_host") not in addresses:
            # The connection tester hasn't verified one of this game's
            # addresses yet: what's there is nothing, or the last game's
            # server. Without one FS-UAE would quietly start offline.
            first = addresses[0] if addresses else ""
            self.game_warning(
                f"the game server's address is not verified yet; "
                f"trying {first}"
            )
            LauncherConfig.set("__netplay_host", first)
        self.do_start_game()

    def do_start_game(self):
        self.game_info("starting game!")

        # we now reset __netplay_addresses so that the ConnectionTester
        # does not connect to the game in progress
        LauncherConfig.set("__netplay_addresses", "")
        from ..launcherapp import LauncherApp

        LauncherApp.start_local_game()

        # game done, resetting config as the same game server cannot be
        # used again
        self.reset_netplay_config()

    def announce_session(self):
        if self.session is None or not self.session.is_host:
            return
        if not self.game_channel or self.session_lobby is None:
            return
        self.irc.channel(self.game_channel).privmsg(
            f"{SESSION_ANNOUNCE} {self.session_lobby} {self.session.game_id}"
        )

    def on_session_announce(self, nick, arg):
        """An op announced a lobby game: join it, off the UI thread."""
        try:
            lobby, game_id = arg.split(" ")
            host, port = parse_lobby(lobby)
        except ValueError:
            self.game_warning(f"ignored a malformed game announcement: {arg}")
            return
        if self.session is not None and self.session.game_id == game_id:
            return
        if self.joining == game_id:
            return  # announced again while the join is on its way
        self.end_session()
        self.joining = game_id
        generation = self.session_generation
        self.game_info(f"{nick} is hosting game {game_id[:8]}; joining")
        client = LobbyClient(host, port)
        tag = self.irc.my_nick[:MAX_TAG_LENGTH]

        def join():
            try:
                joined, error = client.join(game_id, tag), None
            except Exception as e:
                joined, error = None, e
            call_after(joined_game, joined, error)

        def joined_game(joined, error):
            if generation != self.session_generation:
                # Reset, left the channel, disconnected or joined another
                # game meanwhile: hand the slot back rather than follow it.
                if error is None:
                    leave_quietly(joined)
                return
            self.joining = None
            if error is not None:
                self.game_warning(f"could not join game {game_id}: {error}")
                return
            self.begin_session(
                client, game_id, joined["slot"], joined["player_token"]
            )

        def leave_quietly(joined):
            def leave():
                try:
                    client.leave(
                        game_id, joined["slot"], joined["player_token"]
                    )
                except Exception:
                    pass  # the idle reaper frees it anyway

            threading.Thread(
                target=leave, name="lobby-leave", daemon=True
            ).start()

        threading.Thread(target=join, name="lobby-join", daemon=True).start()

    def create_session(self, channel, client, players, password, announce):
        """Create a lobby game as its host; returns False on failure.

        announce is the host:port players' launchers reach the lobby at.
        """
        try:
            created = client.create_game(
                players,
                password,
                self.irc.my_nick[:MAX_TAG_LENGTH],
                LauncherConfig.sync_keys_list,
                LauncherConfig.checksum_keys,
            )
        except Exception as e:
            channel.warning(f"could not create the game: {e}")
            return False
        LauncherConfig.set_multiple(
            [
                ("__netplay_game", created["id"]),
                ("__netplay_password", created["password"]),
                ("__netplay_players", str(created["players"])),
                ("__netplay_port", created["port"]),
                ("__netplay_host", ""),
                ("__netplay_addresses", ",".join(created["addresses"])),
            ]
        )
        self.begin_session(
            client,
            created["id"],
            created["slot"],
            created["player_token"],
            host_token=created["host_token"],
            sync_keys=LauncherConfig.sync_keys_list,
        )
        self.session_lobby = announce
        channel.info(
            f"started game id: {created['id']} password: {created['password']} "
            f"server: {','.join(created['addresses'])} port: {created['port']}"
        )
        self.announce_session()
        return True

    # --- Config and IRC ---------------------------------------------------

    def on_config(self, key, value):
        if key == "__netplay_host_last_error" and value:
            self.game_warning("problem connecting to game server: " + value)
        elif key == "__netplay_host":
            if value:
                self.game_info(
                    "successfully connected to net play host: " + value
                )
        if self.session is not None:
            self.session.config_changed(key)

    def game_message(self, message, color=None):
        if not self.game_channel:
            self.irc.warning(
                "game message received (but not "
                "currently in a game channel): " + message
            )
            return
        self.irc.channel(self.game_channel).message(message, color)
        if self.game_channel != self.irc.active_channel_name:
            # also paste message to active console
            self.irc.active_channel().message(message, color)

    def game_warning(self, message):
        self.game_message(message, IRCColor.WARNING)

    def game_info(self, message):
        self.game_message(message, IRCColor.INFO)

    def is_game_channel(self, name):
        return is_game_channel(name)

    def on_irc(self, key, args):
        if key == "joined":
            if self.is_game_channel(args["channel"]):
                if self.game_channel:
                    self.irc.part(self.game_channel)
                self.game_channel = ""
                self.end_session()
                self.reset_netplay_config()
                self.on_join_game_channel(args["channel"])
        elif key == "parted":
            if self.game_channel == args["channel"]:
                self.end_session()
                self.game_channel = ""
                self.reset_netplay_config()
        elif key == "privmsg":
            message = args["message"]
            if (
                message.startswith(SESSION_ANNOUNCE + " ")
                and args["channel"] == self.game_channel
            ):
                channel = self.irc.channel(self.game_channel)
                if args["nick"] != self.irc.my_nick and channel.is_op(
                    args["nick"]
                ):
                    self.on_session_announce(
                        args["nick"], message[len(SESSION_ANNOUNCE) + 1 :]
                    )
        elif key == "join":
            if args["channel"] == self.game_channel:
                # initialize new player
                self.player(args["nick"])
                if args["nick"] == self.irc.my_nick and self.is_op():
                    self.irc.message(
                        "You are the Operator for this game channel."
                    )
                if args["nick"] != self.irc.my_nick and self.is_op():
                    self.irc.handle_command(
                        "/me is the Operator for this game channel."
                    )
                    # One line tells the newcomer's launcher where the game
                    # is; it fetches the config from the lobby itself.
                    self.announce_session()
        elif key == "part":
            if args["channel"] == self.game_channel:
                self.remove_player(args["nick"])

    def on_join_game_channel(self, channel):
        # first we erase config which is not part of the default configuration
        # key set, to avoid some problems
        keys = fsgs.config.values.keys()
        for key in keys:
            if key not in LauncherConfig.default_config:
                LauncherConfig.set(key, "")
        self.game_channel = channel
        # reset list of players
        self.players = {}

    @staticmethod
    def reset_config():
        LauncherConfig.load_default_config()

    @staticmethod
    def reset_netplay_config():
        LauncherConfig.set_multiple(
            [
                ("__netplay_game", ""),
                ("__netplay_password", ""),
                ("__netplay_players", ""),
                ("__netplay_port", ""),
                ("__netplay_addresses", ""),
                ("__netplay_host", ""),
            ]
        )

    # --- Commands ---------------------------------------------------------

    def handle_command(self, command):
        if not command.startswith("/"):
            return False
        args = command[1:].split(" ")
        function_name = "command_" + args[0]
        try:
            function = getattr(self, function_name)
        except AttributeError:
            return False
        else:
            try:
                function(args[1:])
            except Exception:
                self.game_warning(traceback.format_exc())
            return True

    def command_reset(self, args):
        if len(args) != 0:
            self.irc.warning("syntax: /reset")
            return
        self.end_session()
        if self.game_window:
            self.game_window.close()
            self.game_window = None
        self.hosted_game_left_running = False
        self.reset_netplay_config()
        self.connection_tester = None

    # noinspection SpellCheckingInspection
    def command_recheck(self, args):
        if len(args) != 0:
            self.irc.warning("syntax: /recheck")
            return
        if self.session is None:
            self.game_warning("not in a game")
            return
        self.game_info("checking the game's config again")
        self.session.recheck()

    def require_game_channel(self, channel):
        if not self.irc.running:
            return False
        result = self.game_channel and channel.name == self.game_channel
        if not result:
            channel.warning("not in active game channel")
        return result

    # noinspection SpellCheckingInspection
    def command_resetconfig(self, args):
        if len(args) != 0:
            self.irc.warning("syntax: /resetconfig")
            return
        channel = self.irc.active_channel()
        if not self.require_game_channel(channel):
            return
        # A host's reset reaches the others as its next config version.
        channel.info("config reset by request")
        self.reset_config()

    def parse_server_args(self, args, default_port):
        if len(args) == 0:
            return None
        host, port = parse_lobby(args.pop(0), default_port)
        if len(args) > 0:
            players = int(args.pop(0))
        else:
            players = len(self.players)
        if len(args) > 0:
            password = args.pop(0)
        else:
            password = ""
        if len(args) > 0:
            return None
        return host, port, players, password

    # noinspection SpellCheckingInspection
    def command_startserver(self, args):
        return self.command_startgame(args)

    # noinspection SpellCheckingInspection
    def command_startgame(self, args):
        channel = self.irc.active_channel()
        if not self.require_game_channel(channel):
            return
        result = self.parse_server_args(args, HOST_PORT)
        if not result:
            self.irc.warning(
                "usage: /startgame <host>[:<port>] [<players>] [<password>]"
            )
            return
        host, port, players, password = result

        if not channel.is_op():
            self.irc.warning("startgame: you need to be an operator")
            return
        self.end_session()
        self.create_session(
            channel,
            LobbyClient(host, port),
            players,
            password,
            format_lobby(host, port),
        )

    def command_hostgame(self, args):
        channel = self.irc.active_channel()
        if not self.require_game_channel(channel):
            return
        result = self.parse_server_args(args, HOST_PORT)
        if not result:
            self.irc.warning(
                "usage: /hostgame <address>[,<address2>][:<port>] "
                "[<players>] [<password>]"
            )
            return
        addresses, port, players, password = result

        if not channel.is_op():
            self.irc.warning("hostgame: you need to be an operator")
            return
        # Before binding: ending a game we host that hasn't started stops
        # its lobby, which frees the port.
        self.end_session()

        server = self.running_hosted_server()
        if server is not None and (
            server.port != port or server.public_addresses != addresses
        ):
            # The players' addresses are the lobby's, set when it started;
            # restarting it would end the game still running there.
            channel.warning(
                f"a game hosted on port {server.port} is still running. "
                f"/hostgame {server.public_addresses}:{server.port} hosts "
                f"another game alongside it; Stop server ends it"
            )
            return
        if server is not None:
            # Host this game in the same lobby, as /startgame would in a
            # remote one.
            server.players, server.password = players, password
            started = False
        else:
            # A local lobby, so the game is created and run exactly as
            # against a remote one. A lobby game always has a password:
            # with none given, the lobby generates one, which reaches
            # every player in the config.
            server = Server(
                port,
                players,
                password,
                lobby=True,
                public_addresses=addresses,
            )
            started = self.start_hosted_server(server, channel, port)
            if not started:
                return
        # The launcher reaches its own lobby on loopback; players are told
        # the first public address, as the lobby tells them the rest.
        first = addresses.split(",")[0].strip()
        if not self.create_session(
            channel,
            LobbyClient("127.0.0.1", server.port),
            players,
            password,
            format_lobby(first, server.port),
        ):
            if started:
                server.stop()
            return
        self.session_hosted = True
        channel_name = self.irc.get_active_channel()
        self.game_window = self.parent.create_server_view(
            self.parent, server, self.session.game_id, server.port, channel_name
        )
        self.game_window.show()

    def start_hosted_server(self, server, channel, port):
        """Start a /hostgame lobby; False, having said why, if it can't."""
        try:
            server.start()
        except PortInUseError:
            # Waiting would not help: something still running holds it,
            # most likely a lobby or another hosted game.
            channel.privmsg(
                f"ERROR: port {port} is in use. Is a netplay lobby or another "
                f"game running on this machine? Close it, or use "
                f"/hostgame <address>:<port> to pick another port. If a "
                f"lobby is running here, /startgame localhost:{port} uses it."
            )
            return False
        except ServerError as e:
            # Paths and build guidance can exceed IRC's line limit.
            channel.warning(f"ERROR: could not start the netplay server: {e}")
            channel.privmsg(
                "ERROR: could not start the netplay server. "
                "The host's netplay output has details and repair instructions."
            )
            return False
        # A new lobby: no game has been left running in it.
        self.hosted_game_left_running = False
        return True

    # noinspection SpellCheckingInspection
    def command_joingame(self, args):
        """Join a lobby game by hand, when the announcement was missed."""
        channel = self.irc.active_channel()
        if not self.require_game_channel(channel):
            return
        if len(args) != 2:
            self.irc.warning("usage: /joingame <host>[:<port>] <game-id>")
            return
        self.on_session_announce(self.irc.my_nick, " ".join(args))

    def command_set(self, args):
        channel = self.irc.active_channel()
        if not self.require_game_channel(channel):
            return
        if len(args) < 1:
            self.irc.warning("usage: /set <key> [<value>]")
            return
        if not channel.is_op():
            self.irc.warning("set: you need to be an operator")
            return

        key = args[0]
        value = " ".join(args[1:])
        channel.action(f'set option {key} to "{value}"')
        # A host's change reaches the others as its next config version.
        LauncherConfig.set(key, value)
