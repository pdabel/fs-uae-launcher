"""ServerWatcher against a scripted client; LobbyBrowser with fake
watchers, run as the UI thread would."""

import queue
import threading

import pytest
import requests

from launcher.netplay import lobby_browser
from launcher.netplay.lobby_browser import (
    CONNECTING,
    LOCAL,
    NO_LISTING,
    ONLINE,
    UNREACHABLE,
    LobbyBrowser,
    ServerWatcher,
    describe_error,
)
from launcher.netplay.lobby_client import LobbyError


class ScriptedClient:
    """Answers lobby() from a list of listings and errors, then blocks."""

    url = "http://lobby.example:25101"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.more = threading.Event()

    def lobby(self, member, name, since=None):
        self.calls.append((member, name, since))
        if not self.replies:
            self.more.wait(5)
            raise requests.ConnectionError("done")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def listing(revision, games=(), **extra):
    return {
        "revision": revision,
        "games": list(games),
        "id": "lobby-1",
        **extra,
    }


def game(game_id, title, state="created", players=2, joined=1, host="HST"):
    return dict(
        id=game_id,
        title=title,
        state=state,
        players=players,
        joined=joined,
        host=host,
    )


class Recorder:
    def __init__(self):
        self.events: queue.Queue = queue.Queue()

    def on_listing(self, listing):
        self.events.put(("listing", listing["revision"]))

    def on_state(self, state, error, retry_in):
        self.events.put(("state", state, retry_in))

    def take(self, n):
        return [self.events.get(timeout=5) for _ in range(n)]


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(lobby_browser, "RETRY_DELAY", 0.01)
    monkeypatch.setattr(lobby_browser, "MAX_RETRY_DELAY", 0.04)


def watch(client, recorder, name="Dave"):
    watcher = ServerWatcher(
        client, "m1", lambda: name, recorder.on_listing, recorder.on_state
    )
    watcher.start()
    return watcher


def test_watcher_delivers_new_revisions(fast_retry):
    client = ScriptedClient(listing(3), listing(3), listing(5))
    r = Recorder()
    w = watch(client, r)
    assert r.take(4) == [
        ("state", CONNECTING, None),
        ("state", ONLINE, None),
        ("listing", 3),
        ("listing", 5),  # the unchanged answer isn't delivered
    ]
    w.stop()
    client.more.set()
    assert [c[2] for c in client.calls[:3]] == [0, 3, 3]
    assert client.calls[0][:2] == ("m1", "Dave")


def test_watcher_backs_off_and_starts_over(fast_retry):
    down = requests.ConnectionError("Connection refused")
    client = ScriptedClient(
        listing(7),
        down,
        down,
        down,
        LobbyError(502, "bad gateway"),
        listing(1),
    )
    r = Recorder()
    w = watch(client, r)
    events = r.take(9)
    w.stop()
    client.more.set()
    assert events[:3] == [
        ("state", CONNECTING, None),
        ("state", ONLINE, None),
        ("listing", 7),
    ]
    assert [e[2] for e in events[3:7]] == [0.01, 0.02, 0.04, 0.04]
    assert all(e[1] == UNREACHABLE for e in events[3:7])
    assert events[7:] == [("state", ONLINE, None), ("listing", 1)]
    # After a failure the next poll asks for the listing at once: a
    # restarted lobby counts from 1 again.
    assert client.calls[2][2] == 0
    assert client.calls[5][2] == 0


@pytest.mark.parametrize(
    "reply",
    [
        LobbyError(404, "404 page not found"),
        LobbyError(405, "Method Not Allowed"),
        ValueError("Expecting value"),
        {"not": "a listing"},
    ],
)
def test_watcher_stops_on_an_older_server_until_retry(fast_retry, reply):
    client = ScriptedClient(reply, listing(2))
    r = Recorder()
    w = watch(client, r)
    assert r.take(2) == [
        ("state", CONNECTING, None),
        ("state", NO_LISTING, None),
    ]
    with pytest.raises(queue.Empty):
        r.events.get(timeout=0.2)
    assert len(client.calls) == 1
    w.retry()
    assert r.take(3) == [
        ("state", CONNECTING, None),
        ("state", ONLINE, None),
        ("listing", 2),
    ]
    w.stop()
    client.more.set()


def test_retry_cuts_the_backoff_short(monkeypatch):
    monkeypatch.setattr(lobby_browser, "RETRY_DELAY", 30)
    client = ScriptedClient(requests.ConnectionError("refused"), listing(1))
    r = Recorder()
    w = watch(client, r)
    assert r.take(2)[1][:2] == ("state", UNREACHABLE)
    w.retry()
    assert r.take(2) == [("state", ONLINE, None), ("listing", 1)]
    w.stop()
    client.more.set()


def test_describe_error():
    assert describe_error(LobbyError(503, "too many")) == "too many"
    assert describe_error(requests.ConnectTimeout("x")) == "timed out"
    assert (
        describe_error(
            requests.ConnectionError("[Errno 61] Connection refused")
        )
        == "connection refused"
    )


# --- LobbyBrowser ---------------------------------------------------------


class FakeWatcher:
    def __init__(self, client, member, name, on_listing, on_state):
        self.client = client
        self.member = member
        self.name = name
        self.on_listing = on_listing
        self.on_state = on_state
        self.started = self.stopped = False
        self.retried = 0

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def retry(self):
        self.retried += 1


class FakeClient:
    def __init__(self, host, port):
        self.host, self.port = host, port


class UI:
    def __init__(self):
        self.changes = 0
        self.messages = []
        self.now = 100.0

    def dispatch(self, function, *args):
        function(*args)  # already on "the UI thread"

    def on_change(self):
        self.changes += 1

    def on_message(self, text, warning=False):
        self.messages.append((text, warning))


@pytest.fixture
def ui():
    return UI()


@pytest.fixture
def browser(ui):
    return LobbyBrowser(
        name=lambda: "Paul",
        dispatch=ui.dispatch,
        on_change=ui.on_change,
        on_message=ui.on_message,
        member="m1",
        client_factory=FakeClient,
        watcher_factory=FakeWatcher,
        clock=lambda: ui.now,
    )


def online(browser, key, listing):
    watcher = browser.server(key).watcher
    watcher.on_state(ONLINE, None, None)
    watcher.on_listing(listing)
    return watcher


def test_servers_follow_the_list(browser, ui):
    browser.set_servers(["a.example", "b.example:25200"])
    a = browser.server("a.example").watcher
    b = browser.server("b.example:25200").watcher
    assert a.started and (a.client.host, a.client.port) == ("a.example", 25101)
    assert (b.client.host, b.client.port) == ("b.example", 25200)
    assert a.member == "m1" and a.name() == "Paul"

    browser.set_servers(["b.example:25200", "c.example"])
    assert a.stopped and not b.stopped
    assert browser.server("b.example:25200").watcher is b
    assert [s.key for s in browser.servers()] == [
        "b.example:25200",
        "c.example",
    ]

    browser.set_local(25101)
    local = browser.server(LOCAL)
    assert (local.watcher.client.host, local.watcher.client.port) == (
        "127.0.0.1",
        25101,
    )
    assert browser.servers()[0].title == "This computer"
    browser.set_local(None)
    assert local.watcher is None or local.watcher.stopped
    assert browser.server(LOCAL) is None

    browser.stop()
    assert b.stopped


def test_a_removed_watcher_is_ignored(browser, ui):
    browser.set_servers(["a.example"])
    old = browser.server("a.example").watcher
    browser.set_servers([])
    browser.set_servers(["a.example"])
    old.on_state(ONLINE, None, None)
    old.on_listing(listing(1, [game("g1", "Old")]))
    assert browser.server("a.example").state == CONNECTING
    assert browser.games() == []


def test_games_are_merged_and_sorted(browser, ui):
    browser.set_servers(["a.example", "b.example"])
    online(
        browser,
        "a.example",
        listing(
            2,
            [
                game("g1", "Turrican II", state="running", joined=2),
                game("g2", "speedball 2", joined=2),
                game("g3", "Sensible Soccer"),
                game("g4", "Gone", state="ended"),
            ],
            name="Amiga Friday",
        ),
    )
    b = online(
        browser,
        "b.example",
        listing(4, [game("g5", "Lotus")], id="lobby-2"),
    )
    games = browser.games()
    assert [g.id for g in games] == ["g5", "g3", "g2", "g1"]
    assert games[0].server.short_title == "b.example"
    assert games[1].server.title == "Amiga Friday (a.example)"
    assert games[1].server.short_title == "Amiga Friday"
    assert [g.joinable for g in games] == [True, True, False, False]
    assert games[2].full and games[3].running

    # A server that can't be reached hides its games.
    b.on_state(UNREACHABLE, "connection refused", 8)
    assert [g.id for g in browser.games()] == ["g3", "g2", "g1"]
    server = browser.server("b.example")
    assert server.retry_in(ui.now) == 8
    ui.now += 3
    assert server.retry_in(ui.now) == 5
    browser.retry("b.example")
    assert b.retried == 1


def test_one_lobby_at_two_addresses_is_shown_once(browser):
    # This computer's own public address, in the list.
    browser.set_servers(["198.51.100.7"])
    browser.set_local(25101)
    online(browser, LOCAL, listing(1, [game("g1", "Mine")], id="mine"))
    online(
        browser, "198.51.100.7", listing(1, [game("g1", "Mine")], id="mine")
    )
    assert [s.key for s in browser.servers()] == [LOCAL]
    assert [g.id for g in browser.games()] == ["g1"]


def test_activity_messages(browser, ui):
    browser.set_servers(["a.example", "old.example"])
    a = online(browser, "a.example", listing(1, name="Amiga Friday"))
    a.on_state(UNREACHABLE, "connection refused", 2)
    a.on_state(UNREACHABLE, "connection refused", 4)  # said once
    # Back: the watcher starts over, so a listing always follows.
    a.on_state(ONLINE, None, None)
    a.on_listing(listing(1, name="Amiga Friday"))
    browser.server("old.example").watcher.on_state(
        NO_LISTING, "doesn't list games (older server?)", None
    )
    assert ui.messages == [
        ("Connected to Amiga Friday", False),
        ("Can't reach Amiga Friday: connection refused", True),
        ("Connected to Amiga Friday", False),
        ("old.example doesn't list games (older server?)", True),
    ]


def test_presence_on_this_computer(browser, ui):
    browser.set_local(25101)
    local = online(browser, LOCAL, listing(1, presence=True, online=["Paul"]))
    local.on_listing(listing(2, presence=True, online=["Dave", "Paul", "Sam"]))
    local.on_listing(listing(3, presence=True, online=["Paul", "Sam"]))
    assert ui.messages[1:] == [
        ("Dave is online", False),
        ("Sam is online", False),
        ("Dave went offline", False),
    ]
    assert browser.server(LOCAL).online == ["Paul", "Sam"]


def test_this_computer_lost(browser, ui):
    lost = []

    def on_local_lost():
        lost.append(1)
        browser.set_local(None)

    browser.on_local_lost = on_local_lost
    browser.set_local(25101)
    browser.server(LOCAL).watcher.on_state(UNREACHABLE, "refused", 2)
    assert lost == [1]
    assert browser.server(LOCAL) is None
