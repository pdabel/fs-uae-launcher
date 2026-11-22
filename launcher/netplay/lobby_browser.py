"""Browsing lobby servers: every game waiting for players, on every lobby
in the list. See docs/netplay-rooms-design.md.

ServerWatcher long-polls one lobby's listing (POST /lobby) on its own
thread, as SessionWatcher does one game, so a slow or dead server never
holds up the rest. LobbyBrowser owns one watcher per server, plus one for
the lobby on this computer while it runs, and merges what they see into
one list of games. LobbyBrowser runs on the UI thread: the watchers hand
it everything through dispatch.

This module has no launcher dependencies, so it can be tested on its own.
"""

import threading
import time
import uuid

import requests

from .lobby_client import (
    STATE_CONFIGURING,
    STATE_CREATED,
    STATE_READY,
    STATE_RUNNING,
    LobbyClient,
    LobbyError,
)
from .lobby_servers import parse_lobby

# A server that can't be reached is retried after this long at first,
# doubling up to the maximum. Slower than SessionWatcher's: a server being
# browsed is less urgent than a game being played, and a list can hold
# servers that are gone for good.
RETRY_DELAY = 2
MAX_RETRY_DELAY = 60

# A server's state, as the panel shows it.
CONNECTING = "connecting"
ONLINE = "online"
UNREACHABLE = "unreachable"
NO_LISTING = "no_listing"  # an older fsnp-server, or not a lobby at all

# The key of the lobby on this computer, which isn't in the list.
LOCAL = ""
LOCAL_HOST = "127.0.0.1"

JOINABLE_STATES = (STATE_CREATED, STATE_CONFIGURING, STATE_READY)
LISTED_STATES = JOINABLE_STATES + (STATE_RUNNING,)


class ServerWatcher(threading.Thread):
    """Long-polls one lobby's listing until stop().

    on_listing(listing) is called with each new listing, and
    on_state(state, error, retry_in) whenever the server's state changes
    or a retry is scheduled. Both run on this thread. name() is this
    launcher's netplay name, read for every poll so a change reaches
    presence without a restart.

    Like SessionWatcher, stop() can't interrupt a poll in flight; the
    thread is a daemon and delivers nothing once stopped.
    """

    def __init__(self, client, member, name, on_listing, on_state):
        super().__init__(name=f"lobby-browse-{client.url}", daemon=True)
        self.client = client
        self.member = member
        self.player_name = name
        self.on_listing = on_listing
        self.on_state = on_state
        self._stopped = threading.Event()
        self._wake = threading.Event()

    def stop(self):
        self._stopped.set()
        self._wake.set()

    def retry(self):
        """Try again now, rather than when the backoff runs out."""
        self._wake.set()

    @property
    def stopped(self):
        return self._stopped.is_set()

    def run(self):
        since = 0
        delay = RETRY_DELAY
        state = None
        error: Exception
        while not self.stopped:
            self._wake.clear()
            if state is None:
                state = CONNECTING
                self._state(CONNECTING)
            try:
                listing = self.client.lobby(
                    self.member, self.player_name(), since
                )
                check_listing(listing)
            except LobbyError as e:
                if e.status in (404, 405):
                    state = self._no_listing(
                        "doesn't list games (older server?)"
                    )
                    since = 0
                    continue
                error = e
            except (ValueError, KeyError, TypeError):
                # Not JSON, or not a listing: not a lobby we can browse.
                # requests' JSON error is a ValueError too.
                state = self._no_listing("doesn't list games (not a lobby?)")
                since = 0
                continue
            except requests.RequestException as e:
                error = e
            else:
                delay = RETRY_DELAY
                if state != ONLINE:
                    state = ONLINE
                    self._state(ONLINE)
                if listing["revision"] != since:
                    since = listing["revision"]
                    self._deliver(listing)
                continue
            # A restarted lobby counts from 1 again, so start over rather
            # than wait for a revision it may not reach.
            since = 0
            state = UNREACHABLE
            self._state(UNREACHABLE, describe_error(error), delay)
            self._wake.wait(delay)
            delay = min(delay * 2, MAX_RETRY_DELAY)

    def _no_listing(self, error):
        self._state(NO_LISTING, error)
        # Until the list changes, Retry is pressed or the launcher restarts.
        self._wake.wait()
        return None

    def _state(self, state, error=None, retry_in=None):
        if not self.stopped:
            self.on_state(state, error, retry_in)

    def _deliver(self, listing):
        if not self.stopped:
            self.on_listing(listing)


def check_listing(listing):
    """Raise ValueError unless listing looks like POST /lobby's answer."""
    if not isinstance(listing, dict):
        raise ValueError("not a listing")
    if not isinstance(listing["revision"], int):
        raise ValueError("no revision")
    if not isinstance(listing["games"], list):
        raise ValueError("no games")


def describe_error(error):
    """A short reason for the panel: requests' messages run to lines."""
    if isinstance(error, LobbyError):
        return error.message
    if isinstance(error, requests.Timeout):
        return "timed out"
    if isinstance(error, requests.ConnectionError):
        text = str(error).lower()
        if "refused" in text:
            return "connection refused"
        if (
            "name or service" in text
            or "nodename" in text
            or "resolve" in text
        ):
            return "unknown host"
        return "connection failed"
    return str(error) or type(error).__name__


class BrowsedServer:
    """One watched server, as the panel shows it."""

    def __init__(self, key, host, port):
        self.key = key
        self.host = host
        self.port = port
        self.state = CONNECTING
        self.error = None
        self.retry_at = None
        self.listing = None
        self.watcher = None
        # Say "Connected" with the first listing, which has the name.
        self.announce = False

    @property
    def local(self):
        return self.key == LOCAL

    @property
    def lobby_id(self):
        return self.listing.get("id") if self.listing else None

    @property
    def name(self):
        return (self.listing or {}).get("name") or ""

    @property
    def title(self):
        """What the panel calls it: "This computer", the server's name
        with its address, or its address."""
        if self.local:
            return "This computer"
        if self.name:
            return f"{self.name} ({self.key})"
        return self.key

    @property
    def short_title(self):
        if self.local:
            return "This computer"
        return self.name or self.key

    @property
    def games(self):
        if self.state != ONLINE or not self.listing:
            return []
        return [
            g for g in self.listing["games"] if g.get("state") in LISTED_STATES
        ]

    @property
    def presence(self):
        return bool(self.listing and self.listing.get("presence"))

    @property
    def online(self):
        if self.state != ONLINE or not self.listing or not self.presence:
            return []
        return list(self.listing.get("online") or [])

    def retry_in(self, now):
        if self.retry_at is None:
            return None
        return max(0, round(self.retry_at - now))


class BrowsedGame:
    """One game in the merged list."""

    def __init__(self, game, server):
        self.id = game["id"]
        self.title = game.get("title") or "Untitled game"
        self.host = game.get("host") or "?"
        self.state = game.get("state")
        self.players = int(game.get("players") or 0)
        self.joined = int(game.get("joined") or 0)
        self.server = server

    @property
    def running(self):
        return self.state == STATE_RUNNING

    @property
    def full(self):
        return self.joined >= self.players

    @property
    def joinable(self):
        return self.state in JOINABLE_STATES and not self.full

    def __repr__(self):
        return f"<BrowsedGame {self.title!r} on {self.server.key!r}>"


class LobbyBrowser:
    """Watches every lobby server in the list, and this computer's.

    on_change() is called whenever what servers() or games() return may
    have changed; on_message(text, warning) with lines for the activity
    log. Everything runs on the UI thread: dispatch(fn, *args) gets the
    watchers' callbacks there.
    """

    def __init__(
        self,
        name,
        dispatch,
        on_change=lambda: None,
        on_message=lambda text, warning=False: None,
        member=None,
        client_factory=LobbyClient,
        watcher_factory=ServerWatcher,
        clock=time.monotonic,
    ):
        self.member = member or uuid.uuid4().hex
        self._name = name
        self._dispatch = dispatch
        self._on_change = on_change
        self._on_message = on_message
        self._client_factory = client_factory
        self._watcher_factory = watcher_factory
        self._clock = clock
        self._servers = {}  # key -> BrowsedServer, local first
        self._entries = []
        self._local_port = None
        self.on_local_lost = None

    # --- What's watched -----------------------------------------------------

    def set_servers(self, entries):
        """Watch exactly these list entries (as lobby_servers normalises
        them), keeping the watchers of those already watched."""
        self._entries = list(entries)
        for key in list(self._servers):
            if key != LOCAL and key not in self._entries:
                self._remove(key)
        for entry in self._entries:
            if entry not in self._servers:
                try:
                    host, port = parse_lobby(entry)
                except ValueError:
                    continue
                self._add(BrowsedServer(entry, host, port))
        self._reorder()
        self._on_change()

    def set_local(self, port):
        """Watch the lobby on this computer at port, or stop: None."""
        if port == self._local_port:
            return
        if LOCAL in self._servers:
            self._remove(LOCAL)
        self._local_port = port
        if port is not None:
            self._add(BrowsedServer(LOCAL, LOCAL_HOST, port))
        self._reorder()
        self._on_change()

    def retry(self, key):
        server = self._servers.get(key)
        if server is not None and server.watcher is not None:
            server.watcher.retry()

    def stop(self):
        for key in list(self._servers):
            self._remove(key)
        self._local_port = None

    @property
    def entries(self):
        return list(self._entries)

    # --- Views ---------------------------------------------------------------

    def servers(self):
        """Every watched server once: an entry that turns out to be a
        lobby already shown — this computer's own public address, say —
        is left out."""
        shown, ids = [], set()
        for server in self._servers.values():
            if server.lobby_id is not None:
                if server.lobby_id in ids:
                    continue
                ids.add(server.lobby_id)
            shown.append(server)
        return shown

    def games(self):
        """Every listed game on a server that's online: joinable games
        first, then by title."""
        games = [
            BrowsedGame(game, server)
            for server in self.servers()
            for game in server.games
        ]
        games.sort(
            key=lambda g: (
                not g.joinable,
                g.title.casefold(),
                g.host.casefold(),
                g.server.key,
            )
        )
        return games

    def server(self, key):
        return self._servers.get(key)

    def my_name(self):
        return self._name()

    def now(self):
        return self._clock()

    # --- From the watchers, via dispatch --------------------------------------

    def _add(self, server):
        client = self._client_factory(server.host, server.port)

        def on_listing(listing):
            self._dispatch(self._listing, server, watcher, listing)

        def on_state(state, error, retry_in):
            self._dispatch(
                self._state, server, watcher, state, error, retry_in
            )

        watcher = self._watcher_factory(
            client, self.member, self._name, on_listing, on_state
        )
        server.watcher = watcher
        self._servers[server.key] = server
        watcher.start()

    def _remove(self, key):
        server = self._servers.pop(key)
        if server.watcher is not None:
            server.watcher.stop()
            server.watcher = None

    def _reorder(self):
        """This computer first, then the list's order."""
        order = [LOCAL] + self._entries
        self._servers = {
            key: self._servers[key] for key in order if key in self._servers
        }

    def _current(self, server, watcher):
        return (
            server.watcher is watcher
            and self._servers.get(server.key) is server
        )

    def _listing(self, server, watcher, listing):
        if not self._current(server, watcher):
            return
        before = set(server.online) if server.local else None
        server.listing = listing
        if server.announce:
            server.announce = False
            self._on_message(f"Connected to {server.short_title}")
        if before is not None and server.presence:
            self._presence_changed(before, set(server.online))
        self._on_change()

    def _presence_changed(self, before, after):
        me = self.my_name()
        for name in sorted(after - before - {me}):
            self._on_message(f"{name} is online")
        for name in sorted(before - after - {me}):
            self._on_message(f"{name} went offline")

    def _state(self, server, watcher, state, error, retry_in):
        if not self._current(server, watcher):
            return
        previous = server.state
        server.state = state
        server.error = error
        server.retry_at = (
            self._clock() + retry_in if retry_in is not None else None
        )
        if state == ONLINE and previous != ONLINE:
            server.announce = True
        elif state == UNREACHABLE and previous != UNREACHABLE:
            self._on_message(
                f"Can't reach {server.short_title}: {error}", True
            )
            if server.local and self.on_local_lost is not None:
                self.on_local_lost()
                if self._servers.get(server.key) is not server:
                    return  # stopped watching it
        elif state == NO_LISTING and previous != NO_LISTING:
            self._on_message(f"{server.short_title} {error}", True)
        self._on_change()
