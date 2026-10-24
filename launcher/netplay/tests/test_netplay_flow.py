"""Netplay end to end: a host and a player, fake IRC, a real lobby.

Both launchers run in this process and share one launcher config, which
is fine for this: the player applies what the host sent. Lobby calls run
on their real threads; what they hand to the UI thread is queued and
run by the test, as Qt's event loop would.
"""

import queue
import time

import pytest

from fsgs.context import fsgs
from launcher.netplay import netplay as netplay_module
from launcher.netplay.irc_color import IRCColor
from launcher.netplay.lobby_client import LobbyClient
from launcher.netplay.netplay import Netplay, format_lobby, parse_lobby

CHANNEL = "#test-game"


class FakeChannel:
    def __init__(self, irc, name):
        self.irc = irc
        self.name = name
        self.lines = []

    def is_op(self, nick=None):
        return (nick or self.irc.my_nick) in self.irc.ops

    def privmsg(self, message, notice=False, echo=True):
        self.irc.sent.append(message)

    def info(self, message):
        self.lines.append(("info", message))

    def warning(self, message):
        self.lines.append(("warning", message))

    def action(self, message):
        self.lines.append(("action", message))

    def message(self, message, color=None):
        kind = "warning" if color == IRCColor.WARNING else "message"
        self.lines.append((kind, message))


class FakeIRC:
    def __init__(self, nick, ops):
        self.my_nick = nick
        self.ops = set(ops)
        self.running = True
        self.sent = []
        self.channels = {}
        self.active_channel_name = CHANNEL

    def channel(self, name):
        return self.channels.setdefault(name, FakeChannel(self, name))

    def active_channel(self):
        return self.channel(self.active_channel_name)

    def get_active_channel(self):
        return self.active_channel_name

    def is_channel(self, name):
        return name.startswith(("#", "&"))

    def warning(self, message):
        self.active_channel().warning(message)

    def message(self, message, color=None):
        self.active_channel().message(message)

    def handle_command(self, command):
        pass

    def part(self, name):
        pass

    def stop(self):
        self.running = False


class UIThread:
    def __init__(self):
        self.queue = queue.Queue()
        self.ran = []

    def call_after(self, function, *args):
        self.queue.put((function, args))

    def call_later(self, duration_ms, function):
        self.queue.put((function, ()))

    def pump_until(self, condition, timeout=10):
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                raise AssertionError("timed out waiting for the UI")
            try:
                function, args = self.queue.get(timeout=0.05)
            except queue.Empty:
                continue
            function(*args)
            self.ran.append(function.__name__)


@pytest.fixture
def ui(monkeypatch):
    ui = UIThread()
    monkeypatch.setattr(netplay_module, "call_after", ui.call_after)
    monkeypatch.setattr(netplay_module, "call_later", ui.call_later)
    monkeypatch.setattr(fsgs.config, "values", dict(fsgs.config.values))
    # Nothing in the test config names a file; nothing needs finding.
    monkeypatch.setattr(fsgs.file, "find_by_sha1", lambda sha1: "")
    return ui


@pytest.fixture
def launchers(monkeypatch):
    made = []

    def make(nick, ops):
        n = Netplay()
        n.irc = FakeIRC(nick, ops)
        n.game_channel = CHANNEL
        n.launched = []
        monkeypatch.setattr(n, "do_start_game", lambda: n.launched.append(1))
        made.append(n)
        return n

    yield make
    for n in made:
        n.disconnect()


def warnings(netplay):
    return [
        m
        for kind, m in netplay.irc.channel(CHANNEL).lines
        if kind == "warning"
    ]


def test_host_and_player_start_together(lobby_port, ui, launchers):
    host = launchers("HST", ops={"HST"})
    player = launchers("PL2", ops={"HST"})
    lobby = format_lobby("127.0.0.1", lobby_port)

    assert host.create_session(
        host.irc.active_channel(),
        LobbyClient("127.0.0.1", lobby_port),
        2,
        "",
        lobby,
    )
    game_id = host.session.game_id
    announce = host.irc.sent[-1]
    assert announce == f"__session {lobby} {game_id}"

    # A non-op's announcement is ignored; the op's is joined.
    player.on_irc(
        "privmsg",
        {"channel": CHANNEL, "nick": "RANDOM", "message": announce},
    )
    assert player.session is None
    player.on_irc(
        "privmsg", {"channel": CHANNEL, "nick": "HST", "message": announce}
    )
    ui.pump_until(
        lambda: player.session is not None
        and host.session.state == "ready"
        and player.session.state == "ready"
    )
    assert player.session.game_id == game_id
    assert not player.session.is_host
    assert fsgs.config.get("__netplay_game") == game_id

    seen = []
    host.session_listeners.append(seen.append)
    host.start_netplay_game()
    ui.pump_until(lambda: host.launched and player.launched)
    assert seen and seen[-1].state == "running"
    # No connection tester runs here, so the launch says it is using the
    # lobby's address unverified; the launchers share a config, so only
    # the first to launch needs to.
    assert warnings(host) + warnings(player) == [
        "the game server's address is not verified yet; trying 127.0.0.1"
    ]


def test_host_moving_on_keeps_a_running_game(lobby_port, ui, launchers):
    host = launchers("HST", ops={"HST"})
    player = launchers("PL2", ops={"HST"})
    announce = hosted_game(host, lobby_port)
    first = host.session.game_id
    player.on_irc(
        "privmsg", {"channel": CHANNEL, "nick": "HST", "message": announce}
    )
    ui.pump_until(
        lambda: player.session is not None
        and host.session.state == "ready"
        and player.session.state == "ready"
    )
    host.start_netplay_game()
    ui.pump_until(lambda: host.launched and player.launched)

    # The op opens a new game channel and starts a second game there.
    host.on_irc("joined", {"channel": "#second-game"})
    assert host.session is None
    host.irc.active_channel_name = "#second-game"
    host.handle_command(f"/startgame 127.0.0.1:{lobby_port} 2")
    assert host.session.game_id != first

    lobby = LobbyClient("127.0.0.1", lobby_port)
    time.sleep(0.2)  # let a stray end request reach the lobby
    assert lobby.game(first)["state"] == "running"


def test_host_change_clears_ready_until_reapplied(lobby_port, ui, launchers):
    host = launchers("HST", ops={"HST"})
    host.create_session(
        host.irc.active_channel(),
        LobbyClient("127.0.0.1", lobby_port),
        1,
        "",
        format_lobby("127.0.0.1", lobby_port),
    )
    ui.pump_until(lambda: host.session.state == "ready")
    version = host.session.snapshot["config_version"]

    fsgs.config.set("chip_memory", "2048")
    ui.pump_until(
        lambda: host.session.snapshot["config_version"] > version
        and host.session.state == "ready"
    )
    assert host.session.snapshot["config"]["chip_memory"] == "2048"


def test_reset_ends_the_hosted_game(lobby_port, ui, launchers):
    host = launchers("HST", ops={"HST"})
    host.create_session(
        host.irc.active_channel(),
        LobbyClient("127.0.0.1", lobby_port),
        2,
        "",
        format_lobby("127.0.0.1", lobby_port),
    )
    game_id = host.session.game_id
    host.handle_command("/reset")
    assert host.session is None
    client = LobbyClient("127.0.0.1", lobby_port)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.game(game_id)
        except Exception as e:
            assert getattr(e, "status", None) == 404
            break
        time.sleep(0.05)
    else:
        raise AssertionError("game still in the lobby after /reset")


def hosted_game(host, lobby_port, players=2):
    host.create_session(
        host.irc.active_channel(),
        LobbyClient("127.0.0.1", lobby_port),
        players,
        "",
        format_lobby("127.0.0.1", lobby_port),
    )
    return host.irc.sent[-1]


def claimed_slots(lobby_port, game_id):
    snapshot = LobbyClient("127.0.0.1", lobby_port).game(game_id)
    return [s["slot"] for s in snapshot["slots"] if s["status"] != "empty"]


def wait_for(condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.05)


def test_a_join_overtaken_by_reset_gives_its_slot_back(
    lobby_port, ui, launchers
):
    host = launchers("HST", ops={"HST"})
    player = launchers("PL2", ops={"HST"})
    announce = hosted_game(host, lobby_port)
    game_id = host.session.game_id

    player.on_irc(
        "privmsg", {"channel": CHANNEL, "nick": "HST", "message": announce}
    )
    # The join is on its way when the player resets.
    player.handle_command("/reset")
    ui.pump_until(lambda: "joined_game" in ui.ran)
    assert player.session is None
    wait_for(lambda: claimed_slots(lobby_port, game_id) == [0])


def test_an_announcement_repeated_during_a_join_joins_once(
    lobby_port, ui, launchers
):
    host = launchers("HST", ops={"HST"})
    player = launchers("PL2", ops={"HST"})
    announce = hosted_game(host, lobby_port, players=3)
    game_id = host.session.game_id

    for _ in range(2):
        player.on_irc(
            "privmsg", {"channel": CHANNEL, "nick": "HST", "message": announce}
        )
    ui.pump_until(lambda: player.session is not None)
    assert claimed_slots(lobby_port, game_id) == [0, 1]


@pytest.mark.parametrize(
    "known, want, warned",
    [
        ("", "127.0.0.1", True),
        # The last game's server, verified for that game, not this one.
        ("10.9.9.9", "127.0.0.1", True),
        ("::1", "::1", False),
    ],
)
def test_launch_uses_a_verified_address_of_this_game(
    ui, launchers, known, want, warned
):
    player = launchers("PL2", ops={"HST"})
    fsgs.config.set("__netplay_host", known)
    player.launch_session_game(
        {"config": {"__netplay_addresses": "127.0.0.1,::1"}}
    )
    assert player.launched == [1]
    assert fsgs.config.get("__netplay_host") == want
    assert bool(warnings(player)) == warned


@pytest.mark.parametrize(
    "text, want",
    [
        ("lobby.example", ("lobby.example", 25101)),
        ("lobby.example:25200", ("lobby.example", 25200)),
        ("[2001:db8::1]:25200", ("2001:db8::1", 25200)),
        ("[2001:db8::1]", ("2001:db8::1", 25101)),
        ("2001:db8::1", ("2001:db8::1", 25101)),
    ],
)
def test_parse_lobby(text, want):
    assert parse_lobby(text) == want


def test_format_lobby_round_trips():
    for host in ["lobby.example", "2001:db8::1"]:
        assert parse_lobby(format_lobby(host, 25200)) == (host, 25200)
