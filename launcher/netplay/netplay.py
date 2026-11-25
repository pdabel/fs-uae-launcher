"""This launcher's netplay: the lobbies it browses, the game it's in, and
the lobby it runs on this computer. See docs/netplay-rooms-design.md.

Every lobby call runs off the UI thread; what comes back is handed to the
UI thread with call_after. The Net Play tab shows all of it through the
listener lists.
"""

import threading
import time

from fsgs.context import fsgs
from launcher.i18n import gettext

from .config_apply import apply_document
from .connection_tester import ConnectionTester
from .lobby_browser import LOCAL, LOCAL_HOST, LobbyBrowser
from .lobby_client import STATE_ENDED, STATE_RUNNING, LobbyClient, LobbyError
from .lobby_servers import format_lobby, parse_lobby, split_servers
from .session import NetplaySession
from ..launcher_config import LauncherConfig
from ..launcher_settings import LauncherSettings
from ..option import Option
from ..server.Server import PortInUseError, Server, ServerError

# The lobby's limit on a player's tag.
MAX_TAG_LENGTH = 32

# The lobby's limit on a game's title.
MAX_TITLE_LENGTH = 64

# Lines the activity log keeps.
ACTIVITY_LINES = 200

# What joining holds while Host game is creating a game.
HOSTING = "(hosting)"

# Where the Host dialog defaults to: the server last hosted on.
LAST_HOST_SERVER = "netplay_last_host_server"


def call_after(function, *args):
    """Run function on the UI thread. fsui is imported late, and the two
    helpers are module functions, so tests can run Netplay without Qt."""
    import fsui

    fsui.call_after(function, *args)


def call_later(duration_ms, function):
    import fsui

    fsui.call_later(duration_ms, function)


def truncate_utf8(text, length):
    """text cut to at most length bytes of UTF-8, on a character."""
    return text.encode("utf-8")[:length].decode("utf-8", "ignore")


def local_lobby_name():
    """What browsers call the lobby this launcher runs."""
    name = LauncherSettings.get_netplay_name()
    return truncate_utf8(f"{name}'s lobby", MAX_TITLE_LENGTH)


def game_title():
    """The loaded config's name, as the lobby lists the game."""
    title = LauncherSettings.get(Option.CONFIG_NAME).strip()
    return truncate_utf8(title, MAX_TITLE_LENGTH)


class Netplay:
    _current = None

    @classmethod
    def current(cls):
        if cls._current:
            return cls._current
        return None

    def __init__(self):
        self.enabled = False
        self.connection_tester = None
        # The lobby game this launcher is in.
        self.session = None
        # Bumped whenever the session ends or is replaced, so a join or
        # host still in flight can tell it was overtaken; and what it is.
        self.session_generation = 0
        self.joining = None
        # What the panel calls the session's game and where it is, when
        # known: set on joining from the browser or hosting.
        self.session_title = None
        self.session_server = None
        self.session_listed = True
        # Whether the session's game is in the lobby on this computer, and
        # the id of a game left running there, if any: nothing follows that
        # game to say when it ends, so Stop lobby asks.
        self.session_hosted = False
        self.hosted_game_left_running = None
        # The lobby on this computer: started by the first Host game on
        # This computer, and kept between games until Stop lobby.
        self.local_lobby = None
        # Called with the session (or None) whenever it changes.
        self.session_listeners = []
        # Every lobby in the list, and this computer's while it runs;
        # watched from when the Net Play tab is first shown.
        self.browser = LobbyBrowser(
            name=LauncherSettings.get_netplay_name,
            dispatch=lambda function, *args: call_after(function, *args),
            on_change=self.notify_browser,
            on_message=self.activity,
        )
        self.browser.on_local_lost = self.update_local_lobby
        self.browsing = False
        # Called with no arguments whenever the browser's view changes.
        self.browser_listeners = []
        # (time, text, warning) lines, newest last, and who to tell.
        self.activity_log = []
        self.activity_listeners = []

        LauncherConfig.add_listener(self)

        Netplay._current = self

    def connect(self):
        """Start what the Net Play tab needs: the connection tester, which
        finds which of a game's addresses reaches its server, and
        browsing."""
        self.enabled = True
        if self.connection_tester is None:
            self.connection_tester = ConnectionTester()
        self.start_browsing()

    def disconnect(self):
        self.end_session()
        self.stop_browsing()
        if self.connection_tester is not None:
            self.connection_tester.stop()
            self.connection_tester = None
        if self.local_lobby is not None:
            self.local_lobby.stop()
            self.local_lobby = None
        if Netplay._current == self:
            Netplay._current = None
        self.enabled = False
        LauncherConfig.remove_listener(self)

    def is_connected(self):
        return self.enabled

    # --- Browsing lobbies -------------------------------------------------

    def start_browsing(self):
        """Watch every lobby in the list. Once started, watching carries on
        while other tabs show, so this launcher doesn't look offline."""
        if self.browsing:
            return
        self.browsing = True
        LauncherSettings.add_listener(self)
        self.browser.set_servers(
            split_servers(LauncherSettings.get(Option.NETPLAY_SERVERS))
        )
        self.update_local_lobby()

    def stop_browsing(self):
        if self.browsing:
            self.browsing = False
            LauncherSettings.remove_listener(self)
        self.browser.stop()

    def on_setting(self, key, value):
        if key == Option.NETPLAY_SERVERS and self.browsing:
            self.browser.set_servers(split_servers(value))

    def update_local_lobby(self):
        """Watch this computer's lobby while it runs, over loopback."""
        if not self.browsing:
            return
        server = self.running_local_lobby()
        self.browser.set_local(server.port if server is not None else None)

    def notify_browser(self):
        for listener in list(self.browser_listeners):
            listener()

    def activity(self, text, warning=False):
        """A line for the panel's activity log."""
        self.activity_log.append((time.time(), text, warning))
        del self.activity_log[:-ACTIVITY_LINES]
        for listener in list(self.activity_listeners):
            listener(self.activity_log[-1])

    def game_info(self, text):
        self.activity(text)

    def game_warning(self, text):
        self.activity(text, True)

    # --- The lobby game -------------------------------------------------

    def start_requested(self):
        """The launcher's Start while in a game: games start by themselves
        once every player is ready, so say what this one is waiting for.
        Returns the message."""
        if self.session is not None:
            text = self.session.status_line()
        else:
            text = "Joining the game…"
        self.game_info(text)
        return text

    def begin_session(self, client, game_id, slot, player_token, **host):
        """Follow a lobby game; host passes host_token and sync_keys."""
        self.end_session(keep_config=True)
        self.session = NetplaySession(
            client,
            game_id,
            slot,
            player_token,
            apply=(
                apply_document
                if "host_token" in host
                else self.apply_as_player
            ),
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

    def apply_as_player(self, snapshot):
        """Apply the host's config, and make it this launcher's config.

        The host's config replaces the values, but the settings still
        named the game this launcher had loaded: its title, and the saved
        config or database game it came from. Host game would then offer
        that game while sending the host's, and saving would overwrite
        the saved config. So the config takes the game's title and leaves
        its source behind, as an unsaved config does.
        """
        result = apply_document(snapshot)
        title = snapshot.get("title") or self.session_title
        LauncherSettings.set(Option.CONFIG_NAME, title or "Net Play game")
        for key in ("config_path", "config_xml_path", "parent_uuid"):
            LauncherSettings.set(key, "")
        return result

    def end_session(self, keep_config=False):
        """Leave the current game. One that hasn't started is ended — by a
        host, for everyone. A running game carries on: it belongs to the
        players' FS-UAE now (see NetplaySession.leave).

        The game's __netplay_* keys are cleared, or the next Start would
        launch a single-player game as this one. begin_session keeps them:
        the new game has already set its own."""
        session, self.session = self.session, None
        self.session_title = None
        self.session_server = None
        self.session_generation += 1
        self.joining = None
        if session is not None:
            if self.session_hosted and session.started:
                self.hosted_game_left_running = session.game_id
            self.session_hosted = False
            session.leave()
            self.notify_session()
        if not keep_config:
            self.reset_netplay_config()

    def leave_game(self):
        """The panel's Leave (or End game, for a host)."""
        session = self.session
        if session is None and self.joining is None:
            return
        if session is not None:
            what = self.session_title or f"game {session.game_id[:8]}"
            verb = "ended" if session.is_host else "left"
            self.game_info(f"{verb} {what}")
        self.end_session()
        self.notify_session()

    def recheck(self):
        """The panel's Re-check: apply the game's config again."""
        if self.session is None:
            self.game_warning("not in a game")
            return
        self.game_info("checking the game's config again")
        self.session.recheck()

    def on_session_change(self, session: NetplaySession):
        if session is not self.session:
            return
        if session.ended:
            self.session = None
            self.session_title = None
            self.session_server = None
            self.session_hosted = False
            if not session.launched:
                self.reset_netplay_config()
        self.notify_session(session)

    def notify_session(self, session=None):
        for listener in list(self.session_listeners):
            listener(session or self.session)

    def session_message(self, text, warning=False):
        self.activity(text, warning)

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

    # --- Joining ---------------------------------------------------------

    def is_in_game(self, game_id):
        """In it, or on the way: a second click joins once."""
        if self.session is not None and self.session.game_id == game_id:
            return True
        return self.joining == game_id

    def join_game(
        self, host, port, game_id, tag=None, title=None, server=None
    ):
        """Claim a slot in a lobby game, off the UI thread, and follow it.

        This leaves any game this launcher is in first: one game at a
        time. tag defaults to the netplay name; title and server are what
        the panel calls the game and its lobby.
        """
        if self.is_in_game(game_id):
            return
        self.end_session()
        self.joining = game_id
        generation = self.session_generation
        client = LobbyClient(host, port)
        if tag is None:
            tag = LauncherSettings.get_netplay_name()
        tag = truncate_utf8(tag, MAX_TAG_LENGTH)

        def join():
            try:
                joined, error = client.join(game_id, tag), None
            except Exception as e:
                joined, error = None, e
            call_after(joined_game, joined, error)

        def joined_game(joined, error):
            if generation != self.session_generation:
                # Left, disconnected or joined another game meanwhile:
                # hand the slot back rather than follow it.
                if error is None:
                    leave_quietly(joined)
                return
            self.joining = None
            if error is not None:
                self.game_warning(f"could not join game {game_id}: {error}")
                self.notify_session()
                return
            self.begin_session(
                client, game_id, joined["slot"], joined["player_token"]
            )
            self.session_title = title
            self.session_server = server
            self.game_info(
                f"joined {title or 'game ' + game_id[:8]} as player "
                f"{joined['slot'] + 1}"
            )
            self.notify_session()

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
        self.notify_session()

    # --- Hosting ---------------------------------------------------------

    @staticmethod
    def create_game(client, players, password, tag, **options):
        """Create a lobby game as its host. Only calls the lobby, so it
        can run off the UI thread; follow_hosted_game then follows it."""
        return client.create_game(
            players,
            password,
            tag,
            LauncherConfig.sync_keys_list,
            LauncherConfig.checksum_keys,
            **options,
        )

    def follow_hosted_game(self, client, created):
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

    def host_game(self, server, players, listed=True):
        """Host game: the loaded config, for players, on server — LOCAL for
        this computer's lobby, or a list entry. The game starts by itself
        once every player is ready.

        The lobby call runs off the UI thread, as a join does. Returns
        False if it couldn't get that far, having said why.
        """
        if fsgs.amiga.cd_checksums_pending:
            self.game_warning(
                gettext(
                    "CD image checksums are still being calculated; "
                    "wait and try hosting again"
                )
            )
            return False
        title = game_title()
        if server == LOCAL:
            lobby = self.ensure_local_lobby()
            if lobby is None:
                return False
            host, port, label = LOCAL_HOST, lobby.port, "This computer"
        else:
            try:
                host, port = parse_lobby(server)
            except ValueError:
                self.game_warning(f"{server} is not host or host:port")
                return False
            browsed = self.browser.server(server)
            label = browsed.short_title if browsed is not None else server
        LauncherSettings.set(LAST_HOST_SERVER, server)
        self.end_session()
        self.joining = HOSTING
        generation = self.session_generation
        client = LobbyClient(host, port)
        tag = truncate_utf8(
            LauncherSettings.get_netplay_name(), MAX_TAG_LENGTH
        )

        def create():
            try:
                created, error = (
                    self.create_game(
                        client,
                        players,
                        "",
                        tag,
                        listed=listed,
                        title=title,
                        auto_start=True,
                    ),
                    None,
                )
            except Exception as e:
                created, error = None, e
            call_after(created_game, created, error)

        def created_game(created, error):
            if generation != self.session_generation:
                # Left, or another game, meanwhile: end it rather than
                # leave it waiting in the list.
                if error is None:
                    end_quietly(created)
                return
            self.joining = None
            if error is not None:
                self.game_warning(f"could not host {title}: {error}")
                self.notify_session()
                return
            self.follow_hosted_game(client, created)
            self.session_title = title
            self.session_server = label
            self.session_listed = listed
            self.session_hosted = server == LOCAL
            self.game_info(
                f"hosting {title} for {players} players "
                f"({'listed' if listed else 'unlisted'})"
            )
            self.notify_session()

        def end_quietly(created):
            def end():
                try:
                    client.end(created["id"], created["host_token"])
                except Exception:
                    pass  # the idle reaper ends it anyway

            threading.Thread(target=end, name="lobby-end", daemon=True).start()

        threading.Thread(target=create, name="lobby-host", daemon=True).start()
        self.notify_session()
        return True

    # --- The lobby on this computer ----------------------------------------

    def running_local_lobby(self):
        server = self.local_lobby
        if server is None or server.process is None:
            return None
        if server.process.poll() is not None:
            return None
        return server

    def ensure_local_lobby(self):
        """The lobby on this computer, started if it isn't running; None,
        having said why, if it can't run."""
        server = self.running_local_lobby()
        if server is not None:
            return server
        address = LauncherSettings.get(Option.NETPLAY_PUBLIC_ADDRESS).strip()
        if not address:
            self.game_warning(
                "set the address players reach this computer at, in "
                "Settings → Net Play, before hosting on it"
            )
            return None
        port = LauncherSettings.get_netplay_host_port()
        server = Server(
            port,
            0,
            "",
            lobby=True,
            public_addresses=address,
            presence=True,
            name=local_lobby_name(),
        )
        try:
            server.start()
        except PortInUseError:
            self.game_warning(
                f"port {port} is in use. Is another netplay lobby running "
                f"on this computer? Close it, or choose another port in "
                f"Settings → Net Play"
            )
            return None
        except ServerError as e:
            self.game_warning(f"could not start the lobby: {e}")
            return None
        self.local_lobby = server
        self.hosted_game_left_running = None
        self.game_info(f"lobby running on port {server.port}")
        self.update_local_lobby()
        return server

    def local_lobby_address(self):
        """host:port players reach this computer's lobby at, or None."""
        server = self.running_local_lobby()
        if server is None:
            return None
        first = server.public_addresses.split(",")[0].strip()
        if not first:
            return None
        return format_lobby(first, server.port)

    def game_running_in_local_lobby(self):
        """Whether stopping the lobby here would stop a game being played."""
        if self.hosted_game_left_running and self.left_game_still_running():
            return True
        if (
            self.session is not None
            and self.session_hosted
            and self.session.started
        ):
            return True
        local = self.browser.server(LOCAL)
        return any(
            game.running and game.server is local
            for game in self.browser.games()
        )

    def left_game_still_running(self):
        """Ask this computer's lobby about the game left running in it."""
        server = self.running_local_lobby()
        if server is None:
            self.hosted_game_left_running = None
            return False
        client = LobbyClient(LOCAL_HOST, server.port, timeout=2)
        try:
            state = client.game(self.hosted_game_left_running)["state"]
        except LobbyError as e:
            state = STATE_ENDED if e.status == 404 else STATE_RUNNING
        except Exception:
            return True  # can't tell: keep it
        if state == STATE_RUNNING:
            return True
        self.hosted_game_left_running = None
        return False

    def stop_lobby(self):
        """The panel's Stop lobby: ends a game waiting in it, but not one
        being played."""
        lobby = self.running_local_lobby()
        if lobby is None:
            return
        if self.game_running_in_local_lobby():
            self.game_warning(
                "a game is still running in your lobby; stop the lobby "
                "once it's over"
            )
            return
        if self.session is not None and self.session_hosted:
            self.end_session()
        lobby.stop()
        self.local_lobby = None
        self.update_local_lobby()
        self.game_info("stopped the lobby on this computer")
        self.notify_session()

    # --- Config ----------------------------------------------------------

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
