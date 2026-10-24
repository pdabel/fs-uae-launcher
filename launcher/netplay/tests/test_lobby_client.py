"""LobbyClient and SessionWatcher against a fake HTTP session."""

import json
import threading

import pytest
import requests

from launcher.netplay import lobby_client
from launcher.netplay.lobby_client import (
    LobbyClient,
    LobbyError,
    SessionWatcher,
    base_url,
)


class FakeResponse:
    def __init__(self, status, body=None, reason=""):
        self.status_code = status
        self.reason = reason
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return json.loads(self.content)


class FakeSession:
    """Records requests and answers from a queue of responses or errors."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def request(self, method, url, headers, json, timeout):
        self.requests.append(
            dict(
                method=method,
                url=url,
                headers=headers,
                json=json,
                timeout=timeout,
            )
        )
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def client(*replies):
    session = FakeSession(*replies)
    return LobbyClient("lobby.example", 25101, session=session), session


def test_base_url():
    assert base_url("lobby.example", 25101) == "http://lobby.example:25101"
    assert base_url("2001:db8::1", 25101) == "http://[2001:db8::1]:25101"
    assert base_url("[2001:db8::1]", 25101) == "http://[2001:db8::1]:25101"


def test_create_game_sends_key_lists_as_given():
    c, s = client(FakeResponse(201, {"id": "g1", "host_token": "h"}))
    reply = c.create_game(2, "", "HST", ["a", "b"], ("a", "b", "a"))
    assert reply["id"] == "g1"
    r = s.requests[0]
    assert (r["method"], r["url"]) == (
        "POST",
        "http://lobby.example:25101/game",
    )
    assert r["json"] == {
        "players": 2,
        "password": "",
        "tag": "HST",
        "keys": {"sync": ["a", "b"], "checksum": ["a", "b", "a"]},
    }
    assert "Authorization" not in r["headers"]


def test_token_is_a_bearer_header():
    c, s = client(FakeResponse(204))
    assert c.end("g1", "secret-token") is None
    r = s.requests[0]
    assert (r["method"], r["url"]) == (
        "DELETE",
        "http://lobby.example:25101/game/g1",
    )
    assert r["headers"]["Authorization"] == "Bearer secret-token"


def test_set_config_sends_strings():
    c, s = client(FakeResponse(200, {"config_version": 1, "hash": "abc"}))
    c.set_config("g1", "h", {"chip_memory": 512, "amiga_model": "A500"})
    assert s.requests[0]["json"] == {
        "config": {"chip_memory": "512", "amiga_model": "A500"}
    }


def test_report_ready_body():
    c, s = client(FakeResponse(204))
    c.report_ready("g1", 1, "p", 3, "abc", {"x_floppy_drive_0_sha1": "f"})
    r = s.requests[0]
    assert r["url"].endswith("/game/g1/players/1/ready")
    assert r["json"] == {
        "config_version": 3,
        "hash": "abc",
        "missing": {"x_floppy_drive_0_sha1": "f"},
    }


def test_long_poll_waits_longer():
    c, s = client(FakeResponse(200, {}), FakeResponse(200, {}))
    c.game("g1")
    c.game("g1", since=7)
    assert s.requests[0]["url"].endswith("/game/g1")
    assert s.requests[0]["timeout"] == lobby_client.DEFAULT_TIMEOUT
    assert s.requests[1]["url"].endswith("/game/g1?since=7")
    assert s.requests[1]["timeout"] == lobby_client.POLL_TIMEOUT


def test_errors_carry_the_lobby_message():
    c, _ = client(FakeResponse(409, {"error": "every slot is taken"}))
    with pytest.raises(LobbyError) as e:
        c.join("g1", "PL2")
    assert e.value.status == 409
    assert e.value.message == "every slot is taken"


def test_error_without_json_body():
    c, _ = client(FakeResponse(502, None, reason="Bad Gateway"))
    with pytest.raises(LobbyError) as e:
        c.game("g1")
    assert e.value.status == 502
    assert e.value.message == "Bad Gateway"


def snap(revision, state="configuring"):
    return FakeResponse(200, {"revision": revision, "state": state})


def watch(*replies):
    c, s = client(*replies)
    seen, errors = [], []
    w = SessionWatcher(c, "g1", seen.append, errors.append)
    return w, s, seen, errors


@pytest.fixture
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(lobby_client, "RETRY_DELAY", 0)
    monkeypatch.setattr(lobby_client, "MAX_RETRY_DELAY", 0)


def test_watcher_follows_revisions_until_ended():
    w, s, seen, errors = watch(snap(2), snap(2), snap(5), snap(6, "ended"))
    w.run()
    assert [x["revision"] for x in seen] == [2, 5, 6]
    assert seen[-1]["state"] == "ended"
    # Each poll asks for what's after the last revision it delivered.
    assert [r["url"].rsplit("=", 1)[1] for r in s.requests] == [
        "0",
        "2",
        "2",
        "5",
    ]
    assert errors == []


def test_watcher_reports_a_vanished_game_as_ended():
    w, _, seen, _ = watch(
        snap(2), FakeResponse(404, {"error": "no such game"})
    )
    w.run()
    assert seen[-1] == {"id": "g1", "state": "ended"}


def test_watcher_retries_after_errors(no_retry_delay):
    w, _, seen, errors = watch(
        requests.ConnectionError("refused"),
        FakeResponse(503, {"error": "shutting down"}),
        snap(3, "ended"),
    )
    w.run()
    assert len(errors) == 2
    assert isinstance(errors[0], requests.ConnectionError)
    assert errors[1].status == 503
    assert [x["revision"] for x in seen] == [3]


def test_stopped_watcher_delivers_nothing():
    w, _, seen, _ = watch(snap(2), snap(3))
    w.on_snapshot = lambda s: (seen.append(s), w.stop())
    w.run()
    assert [x["revision"] for x in seen] == [2]


def test_watcher_thread_is_a_daemon():
    w, _, _, _ = watch()
    assert w.daemon
    assert isinstance(w, threading.Thread)
