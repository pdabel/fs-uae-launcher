"""Client for the lobby's session API (fsnp-server --lobby, POST /game).

The lobby holds a netplay game's config document and who has applied it;
see "Future: the session owns the config" in
docs/netplay-go-server-design.md for the API. LobbyClient is one blocking
call per endpoint. SessionWatcher long-polls one game on its own thread
and hands every new snapshot to a callback, which runs on that thread:
marshalling onto the UI thread is the caller's job.

This module has no launcher dependencies, so it can be tested on its own.
"""

import threading

import requests

# Every call but the long-poll should answer at once; this only bounds a
# lobby that has stopped answering.
DEFAULT_TIMEOUT = 10

# The lobby answers a long-poll after 25 s unchanged, so wait a little
# longer than that before calling the connection dead.
POLL_TIMEOUT = 35

# A watcher that loses the lobby retries, waiting this long at first and
# doubling up to the maximum.
RETRY_DELAY = 1
MAX_RETRY_DELAY = 10

# Snapshot states, as the lobby reports them.
STATE_CREATED = "created"
STATE_CONFIGURING = "configuring"
STATE_READY = "ready"
STATE_RUNNING = "running"
STATE_ENDED = "ended"

# Slot statuses.
SLOT_EMPTY = "empty"
SLOT_WAITING = "waiting"
SLOT_READY = "ready"
SLOT_MISSING = "missing"
SLOT_MISMATCH = "mismatch"


class LobbyError(Exception):
    """The lobby refused a call; status is the HTTP status."""

    def __init__(self, status, message):
        super().__init__(f"{message} (HTTP {status})")
        self.status = status
        self.message = message


def base_url(host, port):
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"  # an IPv6 literal
    return f"http://{host}:{port}"


class LobbyClient:
    def __init__(self, host, port, session=None, timeout=DEFAULT_TIMEOUT):
        self.url = base_url(host, port)
        self.session = session or requests.Session()
        self.timeout = timeout

    def create_game(self, players, password, tag, sync_keys, checksum_keys):
        """Create a game, the caller in slot 0.

        Returns the lobby's reply: id, password (generated when password
        is empty), players, port, addresses, host_token, slot and
        player_token. checksum_keys is used as given, order and duplicates
        included, since the hash runs over it.
        """
        return self._request(
            "POST",
            "/game",
            body={
                "players": players,
                "password": password,
                "tag": tag,
                "keys": {
                    "sync": list(sync_keys),
                    "checksum": list(checksum_keys),
                },
            },
        )

    def game(self, game_id, since=None):
        """The game's snapshot; with since, waits for a later revision."""
        if since is None:
            return self._request("GET", f"/game/{game_id}")
        return self._request(
            "GET",
            f"/game/{game_id}?since={int(since)}",
            timeout=POLL_TIMEOUT,
        )

    def join(self, game_id, tag):
        """Claim the lowest free slot: returns slot and player_token."""
        return self._request(
            "POST", f"/game/{game_id}/players", body={"tag": tag}
        )

    def leave(self, game_id, slot, token):
        self._request("DELETE", f"/game/{game_id}/players/{slot}", token)

    def set_config(self, game_id, host_token, config):
        """Replace the document: returns config_version and hash.

        The lobby writes the __netplay_* keys it owns itself and refuses a
        document that carries them.
        """
        return self._request(
            "PUT",
            f"/game/{game_id}/config",
            host_token,
            body={"config": {k: str(v) for k, v in config.items()}},
        )

    def report_ready(
        self, game_id, slot, token, config_version, config_hash, missing
    ):
        """Report what applying config_version produced on this machine.

        missing maps each SHA-1 key that couldn't be resolved to its SHA-1,
        as config_apply returns it.
        """
        self._request(
            "POST",
            f"/game/{game_id}/players/{slot}/ready",
            token,
            body={
                "config_version": config_version,
                "hash": config_hash,
                "missing": dict(missing),
            },
        )

    def start(self, game_id, host_token):
        return self._request("POST", f"/game/{game_id}/start", host_token)

    def end(self, game_id, host_token):
        self._request("DELETE", f"/game/{game_id}", host_token)

    def _request(self, method, path, token=None, body=None, timeout=None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = self.session.request(
            method,
            self.url + path,
            headers=headers,
            json=body,
            timeout=timeout or self.timeout,
        )
        if r.status_code >= 400:
            try:
                message = r.json()["error"]
            except Exception:
                message = r.text.strip() or r.reason
            raise LobbyError(r.status_code, message)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()


class SessionWatcher(threading.Thread):
    """Long-polls one game, calling on_snapshot for each new revision.

    Runs until the game ends — the last snapshot it delivers then has
    state "ended", including when the lobby no longer knows the game — or
    until stop(). on_error is called with each failed poll before the
    watcher retries; it is optional. Both callbacks run on this thread.

    stop() can't interrupt a poll already in flight, so the thread may
    outlive it by up to POLL_TIMEOUT; it is a daemon thread, and delivers
    nothing once stopped.
    """

    def __init__(self, client, game_id, on_snapshot, on_error=None):
        super().__init__(name=f"lobby-watch-{game_id[:8]}", daemon=True)
        self.client = client
        self.game_id = game_id
        self.on_snapshot = on_snapshot
        self.on_error = on_error
        self._stopped = threading.Event()

    def stop(self):
        self._stopped.set()

    @property
    def stopped(self):
        return self._stopped.is_set()

    def run(self):
        since = 0
        delay = RETRY_DELAY
        while not self.stopped:
            try:
                snapshot = self.client.game(self.game_id, since)
            except LobbyError as e:
                if e.status == 404:
                    self._deliver({"id": self.game_id, "state": STATE_ENDED})
                    return
                self._failed(e)
            except requests.RequestException as e:
                self._failed(e)
            else:
                delay = RETRY_DELAY
                if snapshot["revision"] > since:
                    since = snapshot["revision"]
                    self._deliver(snapshot)
                if snapshot["state"] == STATE_ENDED:
                    return
                continue
            self._stopped.wait(delay)
            delay = min(delay * 2, MAX_RETRY_DELAY)

    def _deliver(self, snapshot):
        if not self.stopped:
            self.on_snapshot(snapshot)

    def _failed(self, error):
        if self.on_error is not None and not self.stopped:
            self.on_error(error)
