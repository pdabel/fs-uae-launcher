"""Netplay end to end: hosts and players against a real lobby.

The launchers run in this process and share one launcher config, which
is fine for this: a player applies what the host sent. Lobby calls run
on their real threads; what they hand to the UI thread is queued and
run by the test, as Qt's event loop would.
"""

import queue
import time

import pytest

from fsgs.context import fsgs
from launcher.launcher_settings import LauncherSettings
from launcher.netplay import netplay as netplay_module
from launcher.netplay.lobby_browser import LOCAL
from launcher.netplay.lobby_client import LobbyClient, LobbyError
from launcher.netplay.netplay import Netplay, format_lobby, parse_lobby
from launcher.option import Option
from launcher.server import Server as server_module


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
def settings(monkeypatch):
    """Answers the settings these tests set, and the rest as before."""
    values = {
        Option.NETPLAY_NAME: "HST",
        Option.NETPLAY_SERVERS: "",
        Option.CONFIG_NAME: "Sensible Soccer",
    }
    get = LauncherSettings.get
    monkeypatch.setattr(
        LauncherSettings,
        "get",
        classmethod(
            lambda cls, key: values[key] if key in values else get(key)
        ),
    )
    monkeypatch.setattr(
        LauncherSettings,
        "set",
        classmethod(lambda cls, key, value: values.__setitem__(key, value)),
    )
    return values


@pytest.fixture
def launchers(monkeypatch, settings):
    made = []

    def make():
        n = Netplay()
        n.launched = []
        monkeypatch.setattr(n, "do_start_game", lambda: n.launched.append(1))
        made.append(n)
        return n

    yield make
    for n in made:
        n.disconnect()


@pytest.fixture
def local_server(fsnp_server_binary, monkeypatch, settings):
    """Host game on This computer runs the real binary, on a free port."""
    monkeypatch.setattr(
        server_module, "find_server_executable", lambda: fsnp_server_binary
    )
    monkeypatch.setattr(server_module, "log_file_path", lambda: None)
    monkeypatch.setattr(
        LauncherSettings, "get_netplay_host_port", classmethod(lambda cls: 0)
    )
    settings[Option.NETPLAY_PUBLIC_ADDRESS] = "198.51.100.7"


def warnings(netplay):
    return [text for _, text, warning in netplay.activity_log if warning]


def said(netplay, text):
    return any(line == text for _, line, _ in netplay.activity_log)


def claimed_slots(lobby_port, game_id):
    snapshot = LobbyClient("127.0.0.1", lobby_port).game(game_id)
    return [s["slot"] for s in snapshot["slots"] if s["status"] != "empty"]


def wait_for(condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.05)


def gone(client, game_id):
    try:
        client.game(game_id)
    except LobbyError as e:
        return e.status == 404
    return False


def host_ready(host):
    """The host's own slot is ready for the current config."""
    snapshot = host.session.snapshot
    return snapshot is not None and snapshot["slots"][0]["status"] == "ready"


def host_on(host, ui, lobby_port, players=2, listed=True):
    """Host game on the shared lobby; returns the game id."""
    assert host.host_game(
        format_lobby("127.0.0.1", lobby_port), players, listed=listed
    )
    ui.pump_until(lambda: host.session is not None)
    return host.session.game_id


def test_host_and_player_start_together(lobby_port, ui, launchers, settings):
    host = launchers()
    player = launchers()
    lobby = format_lobby("127.0.0.1", lobby_port)

    assert host.host_game(lobby, 2)
    assert host.joining is not None
    ui.pump_until(lambda: host.session is not None)
    game_id = host.session.game_id
    assert (host.session_title, host.session_server) == (
        "Sensible Soccer",
        lobby,
    )
    client = LobbyClient("127.0.0.1", lobby_port)
    snapshot = client.game(game_id)
    assert snapshot["auto_start"] and snapshot["listed"]
    assert snapshot["title"] == "Sensible Soccer"
    assert snapshot["slots"][0]["tag"] == "HST"

    settings[Option.NETPLAY_NAME] = "PL2"
    player.join_game("127.0.0.1", lobby_port, game_id)
    ui.pump_until(
        lambda: player.session is not None and player.session.snapshot
    )
    assert not player.session.is_host
    assert fsgs.config.get("__netplay_game") == game_id

    # Nobody presses Start.
    seen = []
    host.session_listeners.append(seen.append)
    ui.pump_until(lambda: host.launched and player.launched)
    assert client.game(game_id)["state"] == "running"
    assert [s.state for s in seen if s is not None][-1] == "running"
    assert [s["tag"] for s in client.game(game_id)["slots"]] == ["HST", "PL2"]
    # No connection tester runs here, so the launch says it is using the
    # lobby's address unverified; the launchers share a config, so only
    # the first to launch needs to.
    assert warnings(host) + warnings(player) == [
        "the game server's address is not verified yet; trying 127.0.0.1"
    ]


def test_start_while_in_a_game_says_what_it_waits_for(
    lobby_port, ui, launchers
):
    host = launchers()
    host_on(host, ui, lobby_port)
    ui.pump_until(lambda: host_ready(host) and not host.session.sending_config)
    want = "Starts when 1 more player joins and is ready."
    assert host.start_requested() == want
    assert said(host, want)


def test_host_moving_on_keeps_a_running_game(lobby_port, ui, launchers):
    host = launchers()
    player = launchers()
    first = host_on(host, ui, lobby_port)
    player.join_game("127.0.0.1", lobby_port, first)
    ui.pump_until(lambda: host.launched and player.launched)

    # The host hosts another game while the first is played.
    second = host_on(host, ui, lobby_port)
    assert second != first
    client = LobbyClient("127.0.0.1", lobby_port)
    time.sleep(0.2)  # let a stray end request reach the lobby
    assert client.game(first)["state"] == "running"


def test_host_change_clears_ready_until_reapplied(lobby_port, ui, launchers):
    host = launchers()
    host_on(host, ui, lobby_port)
    ui.pump_until(lambda: host_ready(host))
    version = host.session.snapshot["config_version"]

    fsgs.config.set("chip_memory", "2048")
    ui.pump_until(
        lambda: host.session.snapshot["config_version"] > version
        and host_ready(host)
    )
    assert host.session.snapshot["config"]["chip_memory"] == "2048"


def test_end_game_ends_it_for_everyone(lobby_port, ui, launchers):
    host = launchers()
    game_id = host_on(host, ui, lobby_port)
    host.leave_game()
    assert host.session is None
    assert said(host, "ended Sensible Soccer")
    wait_for(lambda: gone(LobbyClient("127.0.0.1", lobby_port), game_id))


def test_join_and_leave(lobby_port, ui, launchers, settings):
    host = launchers()
    player = launchers()
    game_id = host_on(host, ui, lobby_port)

    sessions = []
    player.session_listeners.append(sessions.append)
    settings[Option.NETPLAY_NAME] = "Dave"
    player.join_game(
        "127.0.0.1",
        lobby_port,
        game_id,
        title="Sensible Soccer",
        server="Club",
    )
    assert player.joining == game_id
    player.join_game("127.0.0.1", lobby_port, game_id)  # a second click
    ui.pump_until(lambda: player.session is not None)
    assert (player.session_title, player.session_server) == (
        "Sensible Soccer",
        "Club",
    )
    assert claimed_slots(lobby_port, game_id) == [0, 1]
    tags = [
        s["tag"]
        for s in LobbyClient("127.0.0.1", lobby_port).game(game_id)["slots"]
    ]
    assert tags == ["HST", "Dave"]
    assert said(player, "joined Sensible Soccer as player 2")
    assert sessions and sessions[0] is None  # told it's joining

    player.leave_game()
    assert player.session is None and player.session_title is None
    wait_for(lambda: claimed_slots(lobby_port, game_id) == [0])
    assert said(player, "left Sensible Soccer")


def test_a_join_overtaken_by_leave_gives_its_slot_back(
    lobby_port, ui, launchers
):
    host = launchers()
    player = launchers()
    game_id = host_on(host, ui, lobby_port)

    player.join_game("127.0.0.1", lobby_port, game_id)
    # The join is on its way when the player leaves.
    player.leave_game()
    ui.pump_until(lambda: "joined_game" in ui.ran)
    assert player.session is None
    wait_for(lambda: claimed_slots(lobby_port, game_id) == [0])


def test_joining_another_game_leaves_the_first(lobby_port, ui, launchers):
    player = launchers()
    client = LobbyClient("127.0.0.1", lobby_port)
    first = client.create_game(2, "", "A", ["amiga_model"], ["amiga_model"])
    second = client.create_game(2, "", "B", ["amiga_model"], ["amiga_model"])
    try:
        player.join_game("127.0.0.1", lobby_port, first["id"])
        ui.pump_until(lambda: player.session is not None)
        player.join_game("127.0.0.1", lobby_port, second["id"])
        ui.pump_until(
            lambda: player.session is not None
            and player.session.game_id == second["id"]
        )
        wait_for(lambda: claimed_slots(lobby_port, first["id"]) == [0])
    finally:
        client.end(first["id"], first["host_token"])
        client.end(second["id"], second["host_token"])


def test_hosting_overtaken_by_leave_ends_the_game(
    lobby_port, ui, launchers, settings
):
    settings[Option.CONFIG_NAME] = "Overtaken"
    host = launchers()
    client = LobbyClient("127.0.0.1", lobby_port)

    def overtaken():
        games = client.lobby("m", "x")["games"]
        return [g for g in games if g["title"] == "Overtaken"]

    assert host.host_game(format_lobby("127.0.0.1", lobby_port), 2)
    host.leave_game()  # before the lobby has answered
    ui.pump_until(lambda: "created_game" in ui.ran)
    assert host.session is None
    wait_for(lambda: overtaken() == [])


def test_a_player_browsing_sees_the_hosts_game(
    lobby_port, ui, launchers, settings
):
    lobby = format_lobby("127.0.0.1", lobby_port)
    settings[Option.NETPLAY_SERVERS] = lobby
    settings[Option.CONFIG_NAME] = "Speedball 2"
    host = launchers()
    player = launchers()
    player.start_browsing()
    game_id = host_on(host, ui, lobby_port)

    def listed():
        return [g for g in player.browser.games() if g.id == game_id]

    ui.pump_until(lambda: bool(listed()))
    game = listed()[0]
    assert (game.title, game.host, game.joined, game.players) == (
        "Speedball 2",
        "HST",
        1,
        2,
    )
    assert game.joinable and game.server.key == lobby
    assert any(
        text.startswith("Connected to") for _, text, _ in player.activity_log
    )

    # Removing the server from the list stops watching it.
    player.on_setting(Option.NETPLAY_SERVERS, "")
    assert player.browser.servers() == [] and player.browser.games() == []


def test_an_unlisted_game_is_joined_by_id(lobby_port, ui, launchers, settings):
    settings[Option.NETPLAY_SERVERS] = format_lobby("127.0.0.1", lobby_port)
    host = launchers()
    player = launchers()
    player.start_browsing()
    game_id = host_on(host, ui, lobby_port, listed=False)
    assert not host.session_listed
    ui.pump_until(lambda: bool(player.browser.servers()[0].listing))
    assert game_id not in [g.id for g in player.browser.games()]
    player.join_game("127.0.0.1", lobby_port, game_id)
    ui.pump_until(
        lambda: player.session is not None
        and player.session.snapshot is not None
    )
    assert player.session.snapshot["title"] == "Sensible Soccer"


def test_host_on_this_computer_keeps_the_lobby_between_games(
    local_server, ui, launchers, settings
):
    settings[Option.NETPLAY_NAME] = "Paul"
    settings[Option.CONFIG_NAME] = "Speedball 2"
    host = launchers()
    host.connect()
    assert host.browser.server(LOCAL) is None

    # Without the address players reach this computer at, it can't host.
    settings[Option.NETPLAY_PUBLIC_ADDRESS] = ""
    assert not host.host_game(LOCAL, 2)
    assert host.running_local_lobby() is None
    assert "Settings" in warnings(host)[-1]
    settings[Option.NETPLAY_PUBLIC_ADDRESS] = "198.51.100.7"

    assert host.host_game(LOCAL, 2, listed=False)
    ui.pump_until(lambda: host.session is not None)
    lobby = host.running_local_lobby()
    assert lobby.presence and lobby.name == "Paul's lobby"
    assert host.session_hosted and host.session_server == "This computer"
    assert host.local_lobby_address() == f"198.51.100.7:{lobby.port}"
    assert settings["netplay_last_host_server"] == LOCAL
    local = host.browser.server(LOCAL)
    ui.pump_until(lambda: local.state == "online" and local.listing)
    assert local.listing["name"] == "Paul's lobby"
    assert local.online == ["Paul"]
    assert host.browser.games() == []  # unlisted
    first = host.session.game_id

    # End the game: the lobby stays for the next one.
    host.leave_game()
    assert host.session is None
    assert host.running_local_lobby() is lobby
    assert host.host_game(LOCAL, 2)
    ui.pump_until(lambda: host.session is not None)
    assert host.running_local_lobby() is lobby
    assert host.session.game_id != first
    ui.pump_until(
        lambda: [g.title for g in host.browser.games()] == ["Speedball 2"]
    )

    host.stop_lobby()
    assert host.session is None and host.running_local_lobby() is None
    assert lobby.process is None
    assert host.browser.server(LOCAL) is None


def test_stop_lobby_waits_for_a_game_left_running(
    local_server, ui, launchers, settings
):
    settings[Option.CONFIG_NAME] = "Solo"
    host = launchers()

    assert host.host_game(LOCAL, 1)
    ui.pump_until(lambda: host.launched)  # one player: starts at once
    lobby = host.running_local_lobby()
    game_id, host_token = host.session.game_id, host.session.host_token
    host.leave_game()  # moving on; the game belongs to FS-UAE now
    assert host.hosted_game_left_running == game_id

    host.stop_lobby()
    assert host.running_local_lobby() is lobby
    assert "still running" in warnings(host)[-1]

    client = LobbyClient("127.0.0.1", lobby.port)
    client.end(game_id, host_token)
    ui.pump_until(lambda: gone(client, game_id))
    host.stop_lobby()
    assert host.running_local_lobby() is None
    assert host.hosted_game_left_running is None


def test_disconnect_stops_the_lobby(local_server, ui, launchers):
    host = launchers()
    assert host.host_game(LOCAL, 2)
    ui.pump_until(lambda: host.session is not None)
    process = host.running_local_lobby().process
    host.disconnect()
    assert process.poll() is not None
    assert Netplay.current() is None


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
    player = launchers()
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


def test_a_joined_config_takes_the_games_title_and_drops_its_source(
    lobby_port, ui, launchers, settings
):
    # The player had their own saved game loaded before joining. Left
    # naming it, Host game would offer it while sending the host's config.
    host = launchers()
    player = launchers()
    game_id = host_on(host, ui, lobby_port)
    settings.update(
        {
            Option.CONFIG_NAME: "Mine",
            "config_path": "/configs/Mine.fs-uae",
            "parent_uuid": "mine-uuid",
        }
    )
    player.join_game("127.0.0.1", lobby_port, game_id)
    ui.pump_until(
        lambda: player.session is not None and player.session.applied_version
    )
    assert settings[Option.CONFIG_NAME] == "Sensible Soccer"
    assert settings["config_path"] == settings["parent_uuid"] == ""
    # The host's own config is its loaded game: it keeps its source.
    settings["config_path"] = "/configs/Hosted.fs-uae"
    host.session.recheck()
    ui.pump_until(lambda: host_ready(host))
    assert settings["config_path"] == "/configs/Hosted.fs-uae"
